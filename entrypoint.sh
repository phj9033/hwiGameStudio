#!/bin/bash
# Fix ownership on mounted volumes so appuser can write
chown -R appuser:appuser /app/data /app/projects /app/agents 2>/dev/null || true
mkdir -p /home/appuser/.codex
# Copy host config (read-only mount) to writable location so Codex can update trust entries
if [ -f /home/appuser/.codex-host/config.toml ]; then
    cp /home/appuser/.codex-host/config.toml /home/appuser/.codex/config.toml
fi
chown -R appuser:appuser /home/appuser/.codex

# Drop privileges and run the command as appuser
exec gosu appuser "$@"
