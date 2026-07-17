import asyncio
import json
import uuid

import websockets


async def turn(socket, text: str, session_id: str) -> tuple[str, int]:
    await socket.send(json.dumps({"type": "query", "text": text, "containerTag": "history-test", "sessionId": session_id}))
    answer = ""
    history_count = -1
    while True:
        message = json.loads(await socket.recv())
        if message["type"] == "token":
            answer += message["text"]
        elif message["type"] == "metric" and message.get("name") == "historyMessages":
            history_count = message["count"]
        elif message["type"] == "error":
            raise RuntimeError(message["message"])
        elif message["type"] == "done":
            return answer.strip(), history_count


async def main() -> None:
    session_id = f"history-test-{uuid.uuid4()}"
    async with websockets.connect("ws://127.0.0.1:8787/ws", max_size=20_000_000) as socket:
        first, first_count = await turn(socket, "Remember that the temporary codeword is cobalt. Reply briefly.", session_id)
        second, second_count = await turn(socket, "What was the temporary codeword?", session_id)
    print(f"first_history_messages={first_count}")
    print(f"second_history_messages={second_count}")
    print(f"second_answer={second}")
    if first_count != 0 or second_count != 2 or "cobalt" not in second.lower():
        raise RuntimeError("Ordered conversation history was not preserved")


if __name__ == "__main__":
    asyncio.run(main())
