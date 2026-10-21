#!/bin/sh
set -eu
host=${1:-tv-home}
# stdout belongs exclusively to MCP. Never add banners or use an SSH pseudo-TTY.
exec ssh -T -o BatchMode=yes -o ConnectTimeout=10 \
  -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
  "$host" 'exec "$HOME/tv-remote-mcp/.venv/bin/tv-remote-mcp"'
