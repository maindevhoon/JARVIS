import asyncio
import json
import os
import time

import websockets


async def main() -> None:
    started = time.perf_counter()
    answer = ""
    first_token = None
    warnings = []
    async with websockets.connect("ws://127.0.0.1:8787/ws", max_size=20_000_000) as socket:
        await socket.send(json.dumps({"type":"query", "text":os.getenv("LLM_TEST_QUERY", "In two concise sentences, explain what Jarvis is building."), "containerTag":"hackathon-user"}))
        while True:
            message = json.loads(await socket.recv())
            if message["type"] == "token":
                answer += message["text"]
            elif message["type"] == "metric" and message.get("name") == "firstToken":
                first_token = message["seconds"]
            elif message["type"] == "error":
                if "TTS" in message.get("message", ""):
                    warnings.append(message["message"])
                else:
                    raise RuntimeError(message["message"])
            elif message["type"] == "done":
                break
    if not answer.strip() or first_token is None:
        raise RuntimeError("Text inference did not complete")
    print(f"first_token_seconds={first_token:.2f}")
    print(f"end_to_end_seconds={time.perf_counter() - started:.2f}")
    print(f"answer={answer.strip()}")
    print(f"answer_words={len(answer.split())}")
    print(f"tts_warnings={len(warnings)}")


if __name__ == "__main__":
    asyncio.run(main())
