import asyncio
import os
import signal
from datetime import datetime
from typing import List, Dict
from backend.database import get_db
import backend.config
from backend.services.cli_runner import CLIRunner
from backend.services.prompt_builder import PromptBuilder
from backend.services.token_parser import calculate_cost
from backend.services.output_sanitizer import sanitize_output


class PipelineExecutor:
    """Executes ticket pipelines by running steps and agents in sequence"""

    def __init__(self):
        self.cli_runner = CLIRunner()
        self.prompt_builder = PromptBuilder(agents_dir=backend.config.AGENTS_DIR)

    async def run_ticket(self, ticket_id: int):
        """Run all steps and agents for a ticket.

        Args:
            ticket_id: ID of the ticket to run
        """
        async with get_db(backend.config.DATABASE_PATH) as db:
            # Fetch ticket details
            ticket_row = await db.execute(
                "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
            )
            ticket = await ticket_row.fetchone()
            if not ticket:
                raise ValueError(f"Ticket {ticket_id} not found")

            # Update ticket status to running
            await db.execute(
                "UPDATE tickets SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                ("running", ticket_id)
            )
            await db.commit()

            # Fetch steps in order
            steps_rows = await db.execute(
                "SELECT * FROM ticket_steps WHERE ticket_id = ? ORDER BY step_order",
                (ticket_id,)
            )
            steps = await steps_rows.fetchall()

            # Build project context
            project_row = await db.execute(
                "SELECT * FROM projects WHERE id = ?", (ticket["project_id"],)
            )
            project = await project_row.fetchone()
            project_dir = os.path.join(backend.config.PROJECTS_DIR, project['name'])
            os.makedirs(project_dir, exist_ok=True)
            if not os.path.isdir(os.path.join(project_dir, ".git")):
                import subprocess
                subprocess.run(["git", "init"], cwd=project_dir, capture_output=True)
            project_context = f"Project: {project['display_name']}\nPath: {project_dir}"

            # Execute steps sequentially
            for step in steps:
                step_id = step["id"]

                # Update step status to running
                await db.execute(
                    "UPDATE ticket_steps SET status = ? WHERE id = ?",
                    ("running", step_id)
                )
                await db.commit()

                # Fetch agents for this step
                agents_rows = await db.execute(
                    "SELECT * FROM step_agents WHERE step_id = ?",
                    (step_id,)
                )
                agents = await agents_rows.fetchall()

                # Run all agents in parallel
                agent_tasks = [
                    self._run_agent(
                        agent=agent,
                        project_context=project_context,
                        ticket_title=ticket["title"],
                        ticket_description=ticket["description"],
                        work_dir=os.path.join(backend.config.PROJECTS_DIR, project["name"])
                    )
                    for agent in agents
                ]

                results = await asyncio.gather(*agent_tasks, return_exceptions=True)

                # Check if any agent failed
                agent_failed = False
                for i, result in enumerate(results):
                    if isinstance(result, Exception) or (isinstance(result, dict) and result.get("return_code") != 0):
                        agent_failed = True
                        break

                # Update step status based on results
                if agent_failed:
                    await db.execute(
                        "UPDATE ticket_steps SET status = ? WHERE id = ?",
                        ("failed", step_id)
                    )
                    await db.execute(
                        "UPDATE tickets SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        ("failed", ticket_id)
                    )
                    await db.commit()
                    return  # Stop execution

                # Mark step as completed
                await db.execute(
                    "UPDATE ticket_steps SET status = ? WHERE id = ?",
                    ("completed", step_id)
                )
                await db.commit()

            # All steps completed successfully
            await db.execute(
                "UPDATE tickets SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                ("completed", ticket_id)
            )
            await db.commit()

    async def _run_agent(
        self,
        agent: Dict,
        project_context: str,
        ticket_title: str,
        ticket_description: str,
        work_dir: str
    ) -> Dict:
        """Run a single agent.

        Args:
            agent: Agent database record
            project_context: Project context string
            ticket_title: Ticket title
            ticket_description: Ticket description
            work_dir: Working directory for execution

        Returns:
            Result dictionary from CLI runner
        """
        async with get_db(backend.config.DATABASE_PATH) as db:
            agent_id = agent["id"]

            # Update agent status to running
            await db.execute(
                "UPDATE step_agents SET status = ?, started_at = CURRENT_TIMESTAMP WHERE id = ?",
                ("running", agent_id)
            )
            await db.commit()

            try:
                # Parse context_refs
                import json
                context_refs = json.loads(agent["context_refs"]) if agent["context_refs"] else []

                # Build prompt
                prompt = self.prompt_builder.build_prompt(
                    agent_name=agent["agent_name"],
                    project_context=project_context,
                    ticket_title=ticket_title,
                    ticket_description=ticket_description,
                    step_instruction=agent["instruction"],
                    context_refs=context_refs
                )

                # Get CLI provider command
                provider_row = await db.execute(
                    "SELECT command, api_key_env FROM cli_providers WHERE name = ?",
                    (agent["cli_provider"],)
                )
                provider = await provider_row.fetchone()
                if not provider:
                    raise ValueError(f"CLI provider {agent['cli_provider']} not found")

                # Apply model override from agent frontmatter
                command = provider["command"]
                model_override = self.prompt_builder.get_agent_model(
                    agent["agent_name"], agent["cli_provider"]
                )
                if model_override:
                    command = f"{command} --model {model_override}"

                # Prepare environment variables
                env = {}
                api_key_env = provider["api_key_env"]
                if api_key_env and api_key_env in os.environ:
                    env[api_key_env] = os.environ[api_key_env]

                # Run CLI
                result = await self.cli_runner.run(
                    command=command,
                    prompt=prompt,
                    work_dir=work_dir,
                    env=env
                )

                # Calculate cost
                cost = 0.0
                if result["input_tokens"] and result["output_tokens"]:
                    # Fetch cost rates
                    rate_row = await db.execute(
                        "SELECT input_rate, output_rate FROM cost_rates WHERE provider = ?",
                        (agent["cli_provider"],)
                    )
                    rate = await rate_row.fetchone()
                    if rate:
                        cost = calculate_cost(
                            result["input_tokens"],
                            result["output_tokens"],
                            rate["input_rate"],
                            rate["output_rate"]
                        )

                # Determine status based on return code
                status = "completed" if result["return_code"] == 0 else "failed"

                # Save full stdout to file
                result_path = None
                if result["stdout"]:
                    results_dir = os.path.join(work_dir, "results")
                    os.makedirs(results_dir, exist_ok=True)
                    result_filename = f"step{agent['step_id']}_{agent['agent_name']}_{agent_id}.md"
                    result_path = os.path.join(results_dir, result_filename)
                    with open(result_path, "w", encoding="utf-8") as f:
                        f.write(result["stdout"])

                # Update agent with results
                await db.execute(
                    """UPDATE step_agents
                       SET status = ?, input_tokens = ?, output_tokens = ?, estimated_cost = ?,
                           result_summary = ?, result_path = ?, pid = ?, completed_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (
                        status,
                        result["input_tokens"],
                        result["output_tokens"],
                        cost,
                        sanitize_output(result["stdout"][:1000]) if result["stdout"] else sanitize_output(result["stderr"][:1000]),
                        result_path,
                        result["pid"],
                        agent_id
                    )
                )
                await db.commit()

                return result

            except Exception as e:
                # Mark agent as failed
                await db.execute(
                    """UPDATE step_agents
                       SET status = ?, result_summary = ?, completed_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    ("failed", sanitize_output(str(e)[:1000]), agent_id)
                )
                await db.commit()
                raise

    async def cancel_ticket(self, ticket_id: int):
        """Cancel a running ticket by terminating all running agents.

        Args:
            ticket_id: ID of the ticket to cancel
        """
        async with get_db(backend.config.DATABASE_PATH) as db:
            # Find all running agents with PIDs
            agents_rows = await db.execute(
                """SELECT sa.id, sa.pid
                   FROM step_agents sa
                   JOIN ticket_steps ts ON sa.step_id = ts.id
                   WHERE ts.ticket_id = ? AND sa.status = 'running' AND sa.pid IS NOT NULL""",
                (ticket_id,)
            )
            agents = await agents_rows.fetchall()

            # Send SIGTERM to each running process
            for agent in agents:
                try:
                    os.kill(agent["pid"], signal.SIGTERM)
                except ProcessLookupError:
                    # Process already terminated
                    pass
                except Exception as e:
                    print(f"Error killing process {agent['pid']}: {e}")

            # Update all agents and steps to cancelled
            await db.execute(
                """UPDATE step_agents
                   SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP
                   WHERE step_id IN (SELECT id FROM ticket_steps WHERE ticket_id = ?)
                   AND status IN ('pending', 'running')""",
                (ticket_id,)
            )

            await db.execute(
                """UPDATE ticket_steps
                   SET status = 'cancelled'
                   WHERE ticket_id = ? AND status IN ('pending', 'running')""",
                (ticket_id,)
            )

            await db.execute(
                "UPDATE tickets SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (ticket_id,)
            )

            await db.commit()

    async def retry_ticket(self, ticket_id: int):
        """Retry a failed ticket from the failed step.

        Args:
            ticket_id: ID of the ticket to retry
        """
        async with get_db(backend.config.DATABASE_PATH) as db:
            # Find the first failed step
            step_row = await db.execute(
                """SELECT id, step_order FROM ticket_steps
                   WHERE ticket_id = ? AND status = 'failed'
                   ORDER BY step_order LIMIT 1""",
                (ticket_id,)
            )
            failed_step = await step_row.fetchone()

            if not failed_step:
                raise ValueError(f"No failed step found for ticket {ticket_id}")

            # Reset all steps from the failed step onwards
            await db.execute(
                """UPDATE ticket_steps
                   SET status = 'pending'
                   WHERE ticket_id = ? AND step_order >= ?""",
                (ticket_id, failed_step["step_order"])
            )

            # Reset all agents in those steps and increment retry_count
            await db.execute(
                """UPDATE step_agents
                   SET status = 'pending', started_at = NULL, completed_at = NULL,
                       pid = NULL, result_summary = NULL, retry_count = retry_count + 1
                   WHERE step_id IN (
                       SELECT id FROM ticket_steps
                       WHERE ticket_id = ? AND step_order >= ?
                   )""",
                (ticket_id, failed_step["step_order"])
            )

            # Update ticket status
            await db.execute(
                "UPDATE tickets SET status = 'assigned', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (ticket_id,)
            )

            await db.commit()

        # Re-run the ticket
        await self.run_ticket(ticket_id)
