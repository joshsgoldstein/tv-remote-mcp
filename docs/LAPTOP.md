# Use Home Control during a laptop session

A laptop on your home Wi-Fi is a complete hosting option. Start Home Control when
you want to use your devices, let it run in the background while you work, and
stop it when you're done. An always-on home server is useful for continuous
availability, but occasional use works well on a laptop.

This guide is for Linux/macOS and assumes you've completed the
[README quick start](../README.md#quick-start), including `uv sync --locked`.
Keep using the same checkout and saved configuration.

## Start the dashboard in the background

Open Terminal, change into your checkout, and run:

```sh
cd /absolute/path/to/tv-remote-mcp
./.venv/bin/home-control-web &
home_control_pid=$!
```

Replace the example path with your checkout's actual location. The `&` leaves
the panel running while you use that terminal for other commands. The next line
remembers this session's process so you can stop it later. Server messages may
still appear in the terminal. Keep this terminal window open during the session.

Open **http://127.0.0.1:8765**. The panel stays on localhost and uses your existing
devices, pairing tokens, and kill switches. If this port is already in use, use
the existing Home Control session, or choose another port with `--port 8767`
and open http://127.0.0.1:8767. Do not stop an unrelated service to free the port.

When you're done, run this in the **same terminal**:

```sh
kill "$home_control_pid"
wait "$home_control_pid"
unset home_control_pid
```

A message saying the process terminated is normal. These commands stop only the
process started above. Closing the browser does not stop the panel. No startup
or login service is installed, and the panel does not automatically restart.
Your settings remain saved for the next session; start it again the same way.
If the process already exited or the terminal was closed, inspect the running
processes before stopping anything; don't reuse an old process ID.

## Use only your assistant

For MCP control, configure your client using
[Connect your assistant](../README.md#connect-your-assistant). The MCP client
starts its own server process when it connects, so no web panel or background
terminal command is required. End or disable that MCP server connection in your
client when you're finished. Some clients keep MCP processes running until the
client exits; use that client's connection controls to stop them.

The web and MCP processes share saved settings. Stopping the web panel stops
that panel; a connected assistant can still send commands. Use **Disable all
controls** when you want to block commands across every Home Control entry point.
Re-enable it only when you want control restored.

## Availability while using a laptop

- Keep the laptop awake and connected to the devices' home network. The app
  doesn't prevent sleep. Control becomes unavailable while the laptop sleeps,
  is shut down, or leaves that network.
- After waking or reconnecting, refresh status. If the panel is no longer
  running, start a new session; saved pairing and kill-switch state are retained.
- A laptop away from home needs a server still running inside the home network
  for remote control. See the README's optional private-access setup.
- Initial Samsung pairing still needs someone to choose **Allow** on the TV.

## Give this setup to your assistant

> Set up Home Control on this laptop for occasional use on my home Wi-Fi. Read
> AGENTS.md, docs/AGENT_SETUP.md, and docs/LAPTOP.md. Preserve my settings, start
> the dashboard in the background for this session, open its localhost URL, and
> give me the exact stop command. Keep the session's terminal available and
> don't install a startup service. Leave pairing pending if I can't approve it
> on the TV. Explain how the web panel and my MCP client's connection stop
> separately, and show me the master kill switch.
