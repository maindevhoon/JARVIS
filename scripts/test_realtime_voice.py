import asyncio
import base64
import json
import os
from pathlib import Path
import time

import websockets


async def main() -> None:
    started = time.perf_counter()
    audio_count = 0
    first_audio_seconds = None
    answer = ""
    async with websockets.connect("ws://127.0.0.1:8787/ws", max_size=20_000_000) as socket:
        await socket.send(
            json.dumps(
                {
                    "type": "query",
                    "text": os.getenv(
                        "REALTIME_TEST_QUERY",
                        "In two short sentences, what is this project building?",
                    ),
                    "containerTag": "hackathon-user",
                }
            )
        )
        while True:
            message = json.loads(await socket.recv())
            kind = message["type"]
            if kind == "token":
                answer += message["text"]
            elif kind == "audio":
                audio_count += 1
                if first_audio_seconds is None:
                    first_audio_seconds = message.get("readySeconds")
                if audio_count == 1:
                    path = Path("output/realtime_voice_first_chunk.wav")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(base64.b64decode(message["wav"]))
            elif kind == "error":
                raise RuntimeError(message["message"])
            elif kind == "done":
                break
    print(f"answer={answer.strip()}")
    print(f"audio_chunks={audio_count}")
    print(f"first_audio_seconds={first_audio_seconds}")
    print(f"end_to_end_seconds={time.perf_counter() - started:.2f}")
    if not answer or not audio_count:
        raise RuntimeError("Realtime pipeline did not produce both text and audio")


if __name__ == "__main__":
    asyncio.run(main())
