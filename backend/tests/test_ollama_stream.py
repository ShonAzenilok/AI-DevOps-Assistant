import asyncio
import json

import httpx


async def test_tool_calls_during_stream() -> None:
    payload = {
        "model": "qwen3.5:4b",
        "messages": [{"role": "user", "content": "List all my S3 buckets in us-east-1"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "aws___call_aws",
                    "description": "Execute AWS CLI commands",
                    "parameters": {
                        "type": "object",
                        "properties": {"cli_command": {"type": "string"}},
                        "required": ["cli_command"],
                    },
                },
            }
        ],
        "stream": True,
    }
    tool_calls = None
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", "http://localhost:11434/api/chat", json=payload) as response:
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                chunk = json.loads(line)
                msg = chunk.get("message", {})
                if msg.get("tool_calls"):
                    tool_calls = msg["tool_calls"]
    assert tool_calls is not None


async def test_summary_after_tool() -> None:
    messages = [
        {"role": "user", "content": "List my S3 buckets"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "aws___call_aws",
                        "arguments": {"cli_command": "aws s3api list-buckets"},
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": '{"Buckets":[{"Name":"my-bucket"}]}',
            "name": "aws___call_aws",
        },
    ]
    payload = {"model": "qwen3.5:4b", "messages": messages, "stream": True}
    content = ""
    thinking = ""
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", "http://localhost:11434/api/chat", json=payload) as response:
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                chunk = json.loads(line)
                msg = chunk.get("message", {})
                content += msg.get("content") or ""
                if msg.get("thinking"):
                    thinking += msg["thinking"]
    print("content:", content[:300])
    print("thinking:", thinking[:300])


if __name__ == "__main__":
    asyncio.run(test_summary_after_tool())
