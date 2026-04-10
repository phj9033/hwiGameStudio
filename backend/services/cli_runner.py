import asyncio
import tempfile
import os
from typing import Dict, Optional
from backend.services.token_parser import parse_claude_output, parse_codex_output


class CLIRunner:
    """Executes CLI commands with prompts and captures results"""

    async def run(
        self,
        command: str,
        prompt: str,
        work_dir: str,
        env: Dict[str, str]
    ) -> Dict:
        """Run a CLI command with the given prompt.

        Args:
            command: CLI command to execute
            prompt: Prompt text to send to the CLI
            work_dir: Working directory for execution
            env: Environment variables

        Returns:
            Dict containing:
                - stdout: Standard output
                - stderr: Standard error
                - return_code: Process return code
                - input_tokens: Parsed input token count (or None)
                - output_tokens: Parsed output token count (or None)
                - pid: Process ID
        """
        # Create temp file for prompt
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(prompt)
            temp_file = f.name

        try:
            # Merge environment variables with current environment
            merged_env = os.environ.copy()
            merged_env.update(env)

            auth_mode = os.environ.get("AUTH_MODE", "").lower()
            if auth_mode == "cli":
                # In CLI auth mode, remove API keys so CLIs use OAuth
                merged_env.pop("ANTHROPIC_API_KEY", None)
                merged_env.pop("OPENAI_API_KEY", None)
            elif auth_mode in ("api", "bedrock"):
                # In API/Bedrock mode, pass through relevant env vars
                passthrough_keys = [
                    "OPENAI_CODEX_API_KEY",
                    "OPENAI_API_KEY",
                ]
                if auth_mode == "bedrock":
                    passthrough_keys += [
                        "CLAUDE_CODE_USE_BEDROCK",
                        "ANTHROPIC_MODEL",
                        "ANTHROPIC_BEDROCK_BASE_URL",
                        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
                        "AWS_REGION",
                        "AWS_ACCESS_KEY_ID",
                        "AWS_SECRET_ACCESS_KEY",
                        "AWS_SESSION_TOKEN",
                    ]
                for key in passthrough_keys:
                    val = os.environ.get(key)
                    if val:
                        merged_env.setdefault(key, val)

            # Execute command with prompt file via stdin
            import shlex
            cmd_parts = shlex.split(command)

            with open(temp_file, 'r') as stdin_file:
                process = await asyncio.create_subprocess_exec(
                    *cmd_parts,
                    stdin=stdin_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=work_dir,
                    env=merged_env
                )

            pid = process.pid

            # Wait for completion and capture output
            stdout_bytes, stderr_bytes = await process.communicate()
            stdout = stdout_bytes.decode('utf-8', errors='replace')
            stderr = stderr_bytes.decode('utf-8', errors='replace')

            # Parse token counts from output
            # Try parsing based on command type
            if 'claude' in command.lower():
                token_info = parse_claude_output(stdout + stderr)
            elif 'codex' in command.lower():
                token_info = parse_codex_output(stdout + stderr)
            else:
                # Generic parsing
                token_info = parse_claude_output(stdout + stderr)

            return {
                "stdout": stdout,
                "stderr": stderr,
                "return_code": process.returncode,
                "input_tokens": token_info["input_tokens"],
                "output_tokens": token_info["output_tokens"],
                "pid": pid
            }

        finally:
            # Clean up temp file
            if os.path.exists(temp_file):
                os.unlink(temp_file)
