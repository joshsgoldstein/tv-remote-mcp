"""Test the real MCP-over-SSH connection using only Python's standard library."""

import argparse
import json
import selectors
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="tv-home", help="SSH host or alias")
    parser.add_argument("--tv-id", help="Optionally check live status for a configured TV")
    args = parser.parse_args()
    process = subprocess.Popen(
        [
            "ssh",
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            args.host,
            'exec "$HOME/tv-remote-mcp/.venv/bin/tv-remote-mcp"',
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        bufsize=0,
    )
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    buffer = b""

    def send(message):
        process.stdin.write((json.dumps({"jsonrpc": "2.0", **message}) + "\n").encode())

    def request(request_id, method, params):
        nonlocal buffer
        send({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if b"\n" not in buffer:
                if not selector.select(timeout=max(0, deadline - time.monotonic())):
                    break
                chunk = process.stdout.read(65536)
                if not chunk:
                    raise RuntimeError("MCP process closed stdout")
                buffer += chunk
                continue
            line, buffer = buffer.split(b"\n", 1)
            message = json.loads(line)
            if message.get("id") == request_id:
                assert "error" not in message, message
                return message["result"]
        raise TimeoutError(f"MCP request timed out: {method}")

    try:
        result = request(
            1,
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "tv-remote-smoke", "version": "1.0"},
            },
        )
        print("Initialized:", result["serverInfo"])
        send({"method": "notifications/initialized"})
        tools = request(2, "tools/list", {})["tools"]
        assert len(tools) == 20, [tool["name"] for tool in tools]
        print("Tools:", ", ".join(tool["name"] for tool in tools))
        calls = [(3, "list_tvs", {})]
        if args.tv_id:
            calls.append((4, "tv_status", {"tv_id": args.tv_id}))
        for request_id, name, arguments in calls:
            result = request(request_id, "tools/call", {"name": name, "arguments": arguments})
            assert not result.get("isError"), result
            print(name, json.dumps(result, indent=2))
        result = request(
            5,
            "tools/call",
            {
                "name": "press_key",
                "arguments": {"tv_id": args.tv_id or "unused", "key": "KEY_FACTORY"},
            },
        )
        assert result.get("isError"), "Service-menu keys must be rejected"
        print("Invalid key safely rejected. MCP smoke test passed.")
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        selector.close()
        process.stdout.close()


if __name__ == "__main__":
    main()
