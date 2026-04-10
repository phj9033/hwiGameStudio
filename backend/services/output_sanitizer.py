import os
import re

# Environment variable names that contain secrets
SECRET_ENV_KEYS = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_CODEX_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_ACCESS_KEY_ID",
]

# Regex patterns for common secret formats
SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),      # Anthropic API key
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),            # OpenAI API key
    re.compile(r"ck-[A-Za-z0-9_-]{20,}"),            # Codex API key
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),              # GitHub PAT
    re.compile(r"AKIA[A-Z0-9]{16}"),                  # AWS Access Key ID
]


def sanitize_output(text: str) -> str:
    """Remove secret values and patterns from CLI output."""
    if not text:
        return text

    # 1) Redact actual env var values found in output
    for key in SECRET_ENV_KEYS:
        value = os.environ.get(key, "")
        if value and len(value) >= 8 and value in text:
            text = text.replace(value, f"[REDACTED:{key}]")

    # 2) Redact known secret patterns
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)

    return text
