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

            # Execute command with prompt from temp file
            full_command = f"{command} < {temp_file}"

            process = await asyncio.create_subprocess_shell(
                full_command,
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
