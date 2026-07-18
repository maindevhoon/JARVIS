import asyncio

import httpx


BASE_URL = "http://127.0.0.1:8787"
SEGMENTS = [
    ("00:04", "Maya", "We need a clear answer on whether a small team can compete with OpenAI on a one-thousand-dollar validation budget."),
    ("00:18", "Dev", "I will research the narrow market opportunity, available model APIs, distribution, and the main risks before Friday."),
    ("00:31", "Maya", "Good. Do not claim we can train a frontier model. Focus on a useful product built on existing infrastructure."),
]


async def main() -> None:
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(f"{BASE_URL}/meetings/sessions", json={"title": "Meeting capture smoke test", "screen": True, "systemAudio": True, "microphone": True})
        response.raise_for_status()
        session = response.json()
        for timestamp, source, text in SEGMENTS:
            response = await client.post(f"{BASE_URL}/meetings/sessions/{session['sessionId']}/transcript", json={"timestamp": timestamp, "source": source, "text": text})
            response.raise_for_status()
            if response.json().get("error"):
                raise RuntimeError(response.json()["error"])
        response = await client.post(f"{BASE_URL}/meetings/sessions/{session['sessionId']}/finish")
        response.raise_for_status()
        finished = response.json()
        if finished["status"] != "completed":
            raise RuntimeError(finished.get("error") or "Meeting summary failed")
        summary = finished["result"]["summary"]
        if not summary.get("summary") or not finished["result"].get("supermemoryDocumentId"):
            raise RuntimeError("Summary or Supermemory document is missing")
        print(f"session_id={session['sessionId']}")
        print(f"title={summary.get('title')}")
        print(f"decisions={len(summary.get('decisions', []))}")
        print(f"actions={len(summary.get('actionItems', []))}")
        print(f"stored_document={finished['result']['supermemoryDocumentId']}")


if __name__ == "__main__":
    asyncio.run(main())
