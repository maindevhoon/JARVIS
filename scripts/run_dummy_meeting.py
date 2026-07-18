import asyncio
import json
import os

import httpx


BASE_URL = "http://127.0.0.1:8787"
FIXTURE = os.getenv("MEETING_FIXTURE", "fixtures/dummy_meeting.json")


async def main() -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{BASE_URL}/meeting/simulate", json={"fixture": FIXTURE}
        )
        response.raise_for_status()
        job = response.json()
        job_id = job["jobId"]
        print(f"job_id={job_id}")
        last_event_count = 0
        while job["status"] in {"queued", "running"}:
            for event in job["events"][last_event_count:]:
                print(f"[{event['stage']}] {event['message']}")
            last_event_count = len(job["events"])
            await asyncio.sleep(1)
            response = await client.get(f"{BASE_URL}/meeting/jobs/{job_id}")
            response.raise_for_status()
            job = response.json()
        for event in job["events"][last_event_count:]:
            print(f"[{event['stage']}] {event['message']}")
        if job["status"] != "completed":
            raise RuntimeError(job.get("error") or "Meeting job failed")
        result = job["result"]
        action_count = len(result["extraction"].get("actionItems", []))
        report_count = len(result["reports"])
        print(f"action_items={action_count}")
        print(f"research_reports={report_count}")
        print(f"elapsed_seconds={result['elapsedSeconds']}")
        print(json.dumps(result["reports"], indent=2))
        if action_count < 1 or report_count != 1:
            raise RuntimeError("Expected at least one user-owned action and exactly one research report")
        report = result["reports"][0]
        valid_source_ids = {source["sourceId"] for source in report.get("sources", [])}
        if report.get("conclusion") not in {"yes", "no", "only-if"}:
            raise RuntimeError("Research conclusion is not normalized")
        if not report.get("citations") or not set(report["citations"]).issubset(valid_source_ids):
            raise RuntimeError("Research report contains missing or invalid citations")


if __name__ == "__main__":
    asyncio.run(main())
