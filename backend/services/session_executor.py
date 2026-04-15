import asyncio
import json
import os
import signal
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import backend.config
from backend.database import get_db
from backend.services.cli_runner import CLIRunner
from backend.services.output_sanitizer import sanitize_output
from backend.services.prompt_builder import PromptBuilder


class SessionExecutor:
    """Parallel execution engine for agent sessions.

    Replaces the sequential PipelineExecutor.  Each agent session runs as an
    independent CLI subprocess.  Sessions declare *depends_on* (files they
    need) and *produces* (files they create).  The orchestrator polls for
    completed files and launches waiting sessions when their dependencies are
    satisfied.
    """

    def __init__(
        self,
        max_parallel: int = 5,
        projects_dir: str = "projects",
        poll_interval: float = 5,
    ):
        self.max_parallel = max_parallel
        self.projects_dir = projects_dir
        self.poll_interval = poll_interval
        self.cli_runner = CLIRunner()
        self.prompt_builder = PromptBuilder(agents_dir=backend.config.AGENTS_DIR)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute_ticket(self, ticket_id: int):
        """Main entry point: execute all sessions for a ticket in parallel."""

        async with get_db(backend.config.DATABASE_PATH) as db:
            # Fetch ticket
            row = await db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
            ticket = await row.fetchone()
            if not ticket:
                raise ValueError(f"Ticket {ticket_id} not found")

            # Fetch project
            prow = await db.execute("SELECT * FROM projects WHERE id = ?", (ticket["project_id"],))
            project = await prow.fetchone()

            # Fetch all sessions for this ticket
            srows = await db.execute(
                "SELECT * FROM agent_sessions WHERE ticket_id = ?", (ticket_id,)
            )
            sessions = await srows.fetchall()
            if not sessions:
                return

            # Prepare workspace
            workspace = Path(self.projects_dir) / f"workspace/ticket_{ticket_id}"
            workspace.mkdir(parents=True, exist_ok=True)

            sessions_log_dir = Path(self.projects_dir) / f"sessions/ticket_{ticket_id}"
            sessions_log_dir.mkdir(parents=True, exist_ok=True)

            # Update ticket to running
            await db.execute(
                "UPDATE tickets SET status = 'running', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (ticket_id,),
            )
            await db.commit()

        # Build lookup structures
        session_map: Dict[int, dict] = {}
        for s in sessions:
            session_map[s["id"]] = dict(s)

        # Categorise sessions: those with no deps start immediately
        semaphore = asyncio.Semaphore(self.max_parallel)
        tasks: Dict[int, asyncio.Task] = {}
        completed_files: Set[str] = set()
        # Track which files exist already in workspace
        for f in workspace.iterdir():
            if not f.name.endswith(".writing"):
                completed_files.add(f.name)

        async with get_db(backend.config.DATABASE_PATH) as db:
            for sid, sdata in session_map.items():
                deps = json.loads(sdata["depends_on"]) if sdata["depends_on"] else []
                if not deps:
                    # No dependencies — set to running and launch
                    await db.execute(
                        "UPDATE agent_sessions SET status = 'running', started_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (sid,),
                    )
                    session_map[sid]["status"] = "running"
                else:
                    await db.execute(
                        "UPDATE agent_sessions SET status = 'waiting' WHERE id = ?",
                        (sid,),
                    )
                    session_map[sid]["status"] = "waiting"
            await db.commit()

        # Launch no-dep sessions
        for sid, sdata in session_map.items():
            if sdata["status"] == "running":
                tasks[sid] = asyncio.create_task(
                    self._guarded_run(sid, ticket_id, semaphore, workspace, sessions_log_dir)
                )

        # Poll loop
        while True:
            # Check completed tasks
            done_sids = [sid for sid, t in tasks.items() if t.done()]
            for sid in done_sids:
                task = tasks[sid]
                exc = task.exception() if not task.cancelled() else None
                # Refresh session status from DB
                async with get_db(backend.config.DATABASE_PATH) as db:
                    r = await db.execute("SELECT status, produces FROM agent_sessions WHERE id = ?", (sid,))
                    row = await r.fetchone()
                    session_map[sid]["status"] = row["status"]
                    if row["status"] == "completed":
                        produces = json.loads(row["produces"]) if row["produces"] else []
                        for fname in produces:
                            completed_files.add(fname)

            # Check for waiting sessions whose deps are now met
            newly_launched = False
            async with get_db(backend.config.DATABASE_PATH) as db:
                for sid, sdata in session_map.items():
                    if sdata["status"] != "waiting":
                        continue
                    deps = json.loads(sdata["depends_on"]) if sdata["depends_on"] else []
                    # Check if all deps are satisfied
                    if all(dep in completed_files for dep in deps):
                        await db.execute(
                            "UPDATE agent_sessions SET status = 'running', started_at = CURRENT_TIMESTAMP WHERE id = ?",
                            (sid,),
                        )
                        session_map[sid]["status"] = "running"
                        tasks[sid] = asyncio.create_task(
                            self._guarded_run(sid, ticket_id, semaphore, workspace, sessions_log_dir)
                        )
                        newly_launched = True
                await db.commit()

            # Check for waiting sessions whose upstream deps have failed
            # (the producing session failed, so the file will never appear)
            failed_produces: Set[str] = set()
            for sid, sdata in session_map.items():
                if sdata["status"] == "failed":
                    produces = json.loads(sdata["produces"]) if sdata["produces"] else []
                    for fname in produces:
                        if fname not in completed_files:
                            failed_produces.add(fname)

            async with get_db(backend.config.DATABASE_PATH) as db:
                for sid, sdata in session_map.items():
                    if sdata["status"] != "waiting":
                        continue
                    deps = json.loads(sdata["depends_on"]) if sdata["depends_on"] else []
                    if any(dep in failed_produces for dep in deps):
                        await db.execute(
                            "UPDATE agent_sessions SET status = 'cancelled', "
                            "error_message = 'Upstream dependency failed', "
                            "completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                            (sid,),
                        )
                        session_map[sid]["status"] = "cancelled"
                await db.commit()

            # Are we done?
            all_terminal = all(
                sdata["status"] in ("completed", "failed", "cancelled")
                for sdata in session_map.values()
            )
            if all_terminal:
                break

            await asyncio.sleep(self.poll_interval)

        # Determine final ticket status
        statuses = {sdata["status"] for sdata in session_map.values()}
        if statuses <= {"completed"}:
            final_status = "completed"
        else:
            final_status = "failed"

        async with get_db(backend.config.DATABASE_PATH) as db:
            await db.execute(
                "UPDATE tickets SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (final_status, ticket_id),
            )
            await db.commit()

    async def cancel_ticket(self, ticket_id: int):
        """Cancel all running/waiting/pending sessions for a ticket."""
        async with get_db(backend.config.DATABASE_PATH) as db:
            # Find running sessions with PIDs
            rows = await db.execute(
                "SELECT id, pid FROM agent_sessions WHERE ticket_id = ? AND status = 'running' AND pid IS NOT NULL",
                (ticket_id,),
            )
            running = await rows.fetchall()

            for s in running:
                try:
                    os.kill(s["pid"], signal.SIGTERM)
                except ProcessLookupError:
                    pass
                except Exception:
                    pass

            # Cancel all non-terminal sessions
            await db.execute(
                """UPDATE agent_sessions
                   SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP
                   WHERE ticket_id = ? AND status IN ('pending', 'running', 'waiting')""",
                (ticket_id,),
            )

            await db.execute(
                "UPDATE tickets SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (ticket_id,),
            )
            await db.commit()

        # Clean up .writing files
        workspace = Path(self.projects_dir) / f"workspace/ticket_{ticket_id}"
        if workspace.exists():
            for f in workspace.iterdir():
                if f.name.endswith(".writing"):
                    try:
                        f.unlink()
                    except OSError:
                        pass

    async def retry_session(self, session_id: int):
        """Retry a single failed session and reset downstream dependents."""
        async with get_db(backend.config.DATABASE_PATH) as db:
            row = await db.execute("SELECT * FROM agent_sessions WHERE id = ?", (session_id,))
            session = await row.fetchone()
            if not session:
                raise ValueError(f"Session {session_id} not found")

            ticket_id = session["ticket_id"]
            produces = json.loads(session["produces"]) if session["produces"] else []

            # Delete produced files from workspace
            workspace = Path(self.projects_dir) / f"workspace/ticket_{ticket_id}"
            for fname in produces:
                for p in [workspace / fname, workspace / f"{fname}.writing"]:
                    if p.exists():
                        try:
                            p.unlink()
                        except OSError:
                            pass

            # Reset this session
            deps = json.loads(session["depends_on"]) if session["depends_on"] else []
            new_status = "pending" if not deps else "waiting"
            await db.execute(
                """UPDATE agent_sessions
                   SET status = ?, error_message = NULL, pid = NULL,
                       started_at = NULL, completed_at = NULL,
                       retry_count = retry_count + 1
                   WHERE id = ?""",
                (new_status, session_id),
            )

            # Reset downstream sessions (those that depend on any of this session's produces)
            all_sessions_rows = await db.execute(
                "SELECT id, depends_on FROM agent_sessions WHERE ticket_id = ? AND id != ?",
                (ticket_id, session_id),
            )
            all_sessions = await all_sessions_rows.fetchall()
            for s in all_sessions:
                s_deps = json.loads(s["depends_on"]) if s["depends_on"] else []
                if any(dep in produces for dep in s_deps):
                    await db.execute(
                        """UPDATE agent_sessions
                           SET status = 'waiting', error_message = NULL,
                               pid = NULL, started_at = NULL, completed_at = NULL
                           WHERE id = ?""",
                        (s["id"],),
                    )

            await db.commit()

        # Re-trigger execution for the whole ticket
        await self.execute_ticket(ticket_id)

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    async def _guarded_run(
        self,
        session_id: int,
        ticket_id: int,
        semaphore: asyncio.Semaphore,
        workspace: Path,
        sessions_log_dir: Path,
    ):
        """Acquire semaphore then run the session."""
        async with semaphore:
            await self._run_single_session(session_id, ticket_id, workspace, sessions_log_dir)

    async def _run_single_session(
        self,
        session_id: int,
        ticket_id: int,
        workspace: Path,
        sessions_log_dir: Path,
    ):
        """Run one agent session end-to-end."""
        async with get_db(backend.config.DATABASE_PATH) as db:
            row = await db.execute("SELECT * FROM agent_sessions WHERE id = ?", (session_id,))
            session = await row.fetchone()

            trow = await db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
            ticket = await trow.fetchone()

            prow = await db.execute("SELECT * FROM projects WHERE id = ?", (ticket["project_id"],))
            project = await prow.fetchone()

            # Get provider info
            provrow = await db.execute(
                "SELECT command, api_key_env FROM cli_providers WHERE name = ?",
                (session["cli_provider"],),
            )
            provider = await provrow.fetchone()
            if not provider:
                raise ValueError(f"CLI provider {session['cli_provider']} not found")

        agent_name = session["agent_name"]
        produces = json.loads(session["produces"]) if session["produces"] else []

        # Build prompt
        project_dir = os.path.join(self.projects_dir, project["name"]) if project else str(workspace)
        project_context = f"Project: {project['display_name']}\nPath: {project_dir}" if project else ""

        prompt = self.prompt_builder.build_prompt(
            agent_name=agent_name,
            project_context=project_context,
            ticket_title=ticket["title"],
            ticket_description=ticket["description"] or "",
            step_instruction=session["instruction"],
            context_refs=[],
        )

        # Add workspace context to prompt
        prompt += f"\n\n---\n## Workspace\nPath: {workspace}\n"
        if produces:
            prompt += "You must create the following files (use .writing extension while writing):\n"
            for fname in produces:
                prompt += f"- {workspace / fname}\n"

        # Apply model override
        command = provider["command"]
        model_override = self.prompt_builder.get_agent_model(agent_name, session["cli_provider"])
        if model_override:
            command = f"{command} --model {model_override}"

        # Prepare env
        env = {}
        api_key_env = provider["api_key_env"]
        if api_key_env and api_key_env in os.environ:
            env[api_key_env] = os.environ[api_key_env]

        try:
            result = await self._run_cli(prompt, command, work_dir=str(workspace), env=env)

            pid = result.get("pid")
            # Record PID
            async with get_db(backend.config.DATABASE_PATH) as db:
                await db.execute(
                    "UPDATE agent_sessions SET pid = ? WHERE id = ?", (pid, session_id)
                )
                await db.commit()

            success = result.get("return_code", 1) == 0

            # Save session log
            log_filename = f"{agent_name}_{session_id}.md"
            log_path = sessions_log_dir / log_filename
            stdout = result.get("stdout", "") or ""
            stderr = result.get("stderr", "") or ""
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"# Session {session_id} — {agent_name}\n\n")
                f.write(f"## stdout\n```\n{stdout}\n```\n\n")
                if stderr:
                    f.write(f"## stderr\n```\n{stderr}\n```\n")

            # Handle produces files
            if success:
                for fname in produces:
                    writing_path = workspace / f"{fname}.writing"
                    final_path = workspace / fname
                    if writing_path.exists():
                        writing_path.rename(final_path)
                status = "completed"
                error_msg = None
            else:
                for fname in produces:
                    writing_path = workspace / f"{fname}.writing"
                    if writing_path.exists():
                        try:
                            writing_path.unlink()
                        except OSError:
                            pass
                status = "failed"
                error_msg = sanitize_output((stderr or stdout)[:1000])

            # Update DB
            async with get_db(backend.config.DATABASE_PATH) as db:
                await db.execute(
                    """UPDATE agent_sessions
                       SET status = ?, input_tokens = ?, output_tokens = ?,
                           error_message = ?, session_log_path = ?,
                           completed_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (
                        status,
                        result.get("input_tokens"),
                        result.get("output_tokens"),
                        error_msg,
                        str(log_path),
                        session_id,
                    ),
                )
                await db.commit()

        except Exception as e:
            # Clean up .writing files on exception
            for fname in produces:
                writing_path = workspace / f"{fname}.writing"
                if writing_path.exists():
                    try:
                        writing_path.unlink()
                    except OSError:
                        pass

            async with get_db(backend.config.DATABASE_PATH) as db:
                await db.execute(
                    """UPDATE agent_sessions
                       SET status = 'failed', error_message = ?,
                           completed_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (sanitize_output(str(e)[:1000]), session_id),
                )
                await db.commit()

    async def _run_cli(self, prompt: str, provider: str, **kwargs) -> Dict:
        """Thin wrapper around CLIRunner for test mocking."""
        return await self.cli_runner.run(
            command=provider,
            prompt=prompt,
            work_dir=kwargs.get("work_dir", "."),
            env=kwargs.get("env", {}),
        )
