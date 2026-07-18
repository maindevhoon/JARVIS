import asyncio
import os

import httpx


BASE_URL = "http://127.0.0.1:8787"
QUESTION = os.getenv(
    "RESEARCH_TEST_QUESTION",
    "What capabilities does NVIDIA NIM expose for building a tool-using background research agent?",
)


async def main() -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{BASE_URL}/research/jobs", json={"question": QUESTION})
        response.raise_for_status()
        job = response.json()
        print(f"job_id={job['jobId']}")
        seen = 0
        while job["status"] in {"queued", "running"}:
            for event in job["events"][seen:]:
                print(f"[{event['stage']}] {event['message']}")
            seen = len(job["events"])
            await asyncio.sleep(1)
            response = await client.get(f"{BASE_URL}/research/jobs/{job['jobId']}")
            response.raise_for_status()
            job = response.json()
        for event in job["events"][seen:]:
            print(f"[{event['stage']}] {event['message']}")
        if job["status"] != "completed":
            raise RuntimeError(job.get("error") or "Research job failed")
        report = job["result"]["report"]
        print(f"conclusion={report['conclusion']}")
        print(f"sources={len(report.get('sources', []))}")
        print(f"elapsed_seconds={job['result']['elapsedSeconds']}")
        if not report.get("citations"):
            raise RuntimeError("Completed research has no validated citations")


if __name__ == "__main__":
    asyncio.run(main())
