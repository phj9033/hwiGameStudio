#!/bin/bash
# Fix ownership on mounted volumes so appuser can write
chown -R appuser:appuser /app/data /app/projects /app/agents 2>/dev/null || true
chown -R appuser:appuser /home/appuser/.codex 2>/dev/null || true

# Drop privileges and run the command as appuser
exec gosu appuser "$@"
