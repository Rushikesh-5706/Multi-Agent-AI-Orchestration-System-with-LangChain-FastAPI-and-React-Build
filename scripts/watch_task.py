from __future__ import annotations

import argparse
import json
import sys
import urllib.parse

import requests
import websockets
import asyncio


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch multi-agent workflow execution")
    parser.add_argument("prompt", nargs="?", default="What is the current weather in Tokyo, and based on that, what should I pack?", help="Prompt to submit")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Base API URL")
    return parser.parse_args()


async def stream_events(ws_url: str) -> int:
    exit_code = 0
    try:
        async with websockets.connect(ws_url) as ws:
            async for raw in ws:
                data = json.loads(raw)
                event_type = data.get("event_type")
                if event_type == "HEARTBEAT":
                    continue

                seq = data.get("sequence", "-")
                agent = data.get("agent", "-")
                msg = data.get("message", "")
                print(f"[{seq}] {agent} | {event_type}: {msg}")

                payload = data.get("payload", {})
                if event_type == "TOOL_INVOCATION":
                    print(f"    Tool: {payload.get('tool')} | Args: {payload.get('arguments')}")
                elif event_type == "TOOL_RESULT":
                    print(f"    Result ({payload.get('duration_ms')}ms): {payload.get('result')}")
                elif event_type == "COMPLETED":
                    print("\nFinal Result:")
                    print(payload.get("final_result", msg))
                    return 0
                elif event_type == "ERROR":
                    if payload.get("fatal", False):
                        print(f"Fatal error: {msg}", file=sys.stderr)
                        return 1
    except websockets.exceptions.ConnectionClosedOK:
        return exit_code
    except Exception as exc:
        print(f"WebSocket error: {exc}", file=sys.stderr)
        return 1
    return exit_code


def main() -> int:
    args = parse_args()
    api_url = args.api_url.rstrip("/")
    post_url = f"{api_url}/api/tasks"

    try:
        resp = requests.post(post_url, json={"prompt": args.prompt}, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        print(f"Failed to submit task: {exc}", file=sys.stderr)
        return 1

    task_data = resp.json()
    task_id = task_data.get("task_id")
    if not task_id:
        print(f"Invalid response from server: {task_data}", file=sys.stderr)
        return 1

    print(f"Task initiated: {task_id}")

    parsed = urllib.parse.urlparse(api_url)
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{parsed.netloc}/api/ws/{task_id}"

    return asyncio.run(stream_events(ws_url))


if __name__ == "__main__":
    sys.exit(main())
