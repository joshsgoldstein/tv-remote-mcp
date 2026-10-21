#!/bin/sh
set -eu
host=${1:-tv-home}
cd "$(dirname "$0")/.."
archive=$(mktemp /tmp/tv-remote-deploy.XXXXXX)
trap 'rm -f "$archive"' EXIT HUP INT TERM
tar --exclude='__pycache__' -czf "$archive" \
  pyproject.toml requirements.txt uv.lock src tests scripts examples docs README.md AGENTS.md CONTRIBUTING.md LICENSE config.example.json
ssh -T -o BatchMode=yes -o ConnectTimeout=10 "$host" \
  'mkdir -p ~/tv-remote-mcp && tar -xzf - -C ~/tv-remote-mcp &&
   cd ~/tv-remote-mcp && python3 -m venv .venv &&
   .venv/bin/pip install -r requirements.txt . &&
   umask 077 && mkdir -p ~/.config/tv-remote-mcp/artwork &&
   if [ ! -f ~/.config/tv-remote-mcp/config.json ]; then
     cp config.example.json ~/.config/tv-remote-mcp/config.json
   fi' < "$archive"
