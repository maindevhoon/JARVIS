import asyncio
import base64
import json
from pathlib import Path

import websockets


async def main() -> None:
    sample = Path("output/realtime_voice_first_chunk.wav")
    if not sample.is_file():
        raise RuntimeError(f"Missing speech sample: {sample}")
    async with websockets.connect("ws://127.0.0.1:8787/listen", max_size=20_000_000) as socket:
        await socket.send(
            json.dumps(
                {
                    "type": "transcribe",
                    "audio": base64.b64encode(sample.read_bytes()).decode("ascii"),
                    "mimeType": "audio/wav",
                }
            )
        )
        message = json.loads(await socket.recv())
    if message.get("type") != "transcript" or not message.get("text"):
        raise RuntimeError(message)
    print(f"transcript={message['text']}")
    print(f"transcription_seconds={message['seconds']:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
