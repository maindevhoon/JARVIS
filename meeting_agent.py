from __future__ import annotations

import asyncio
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from uuid import uuid4

import httpx


ROOT = Path(__file__).resolve().parent
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("MEETING_AGENT_MODEL", os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"))
SUPERMEMORY_URL = os.getenv("SUPERMEMORY_URL", "http://127.0.0.1:6767")
MEETING_CONTAINER = os.getenv("MEETING_CONTAINER", "jarvis-meeting-demo")


class SearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._capture: str | None = None
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = values.get("class") or ""
        if tag == "a" and "result__a" in classes:
            self._capture = "title"
            self._href = values.get("href") or ""
            self._text = []
        elif "result__snippet" in classes:
            self._capture = "snippet"
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture == "title" and tag == "a":
            href = self._href
            parsed = urlparse(href)
            if parsed.netloc.endswith("duckduckgo.com"):
                href = unquote(parse_qs(parsed.query).get("uddg", [href])[0])
            self.results.append({"title": " ".join("".join(self._text).split()), "url": href, "snippet": ""})
            self._capture = None
        elif self._capture == "snippet" and tag in {"a", "div", "span"}:
            if self.results:
                self.results[-1]["snippet"] = " ".join("".join(self._text).split())
            self._capture = None


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "svg", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg", "noscript"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            value = " ".join(data.split())
            if value:
                self.text.append(value)


class MeetingAgent:
    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}

    def create_job(self, fixture: str = "fixtures/dummy_meeting.json") -> dict[str, Any]:
        path = (ROOT / fixture).resolve()
        if ROOT not in path.parents or not path.is_file():
            raise ValueError("Meeting fixture must be an existing file inside the project")
        job_id = str(uuid4())
        self.jobs[job_id] = {
            "jobId": job_id,
            "status": "queued",
            "stage": "queued",
            "fixture": str(path.relative_to(ROOT)),
            "events": [{"stage": "queued", "message": "Meeting simulation accepted"}],
            "result": None,
            "error": None,
        }
        asyncio.create_task(self._run(job_id, path))
        return self.jobs[job_id]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self.jobs.get(job_id)

    def _event(self, job: dict[str, Any], stage: str, message: str) -> None:
        job["stage"] = stage
        job["events"].append({"stage": stage, "message": message})

    async def _groq_json(self, system: str, user: str, max_tokens: int = 1400) -> dict[str, Any]:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        payload = {
            "model": GROQ_MODEL,
            "temperature": 0.1,
            "max_completion_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=90) as client:
            for attempt in range(4):
                response = await client.post(GROQ_CHAT_URL, headers=headers, json=payload)
                if response.status_code != 429 or attempt == 3:
                    break
                match = re.search(r"try again in ([0-9.]+)s", response.text, re.IGNORECASE)
                delay = float(match.group(1)) + 1 if match else 10 * (attempt + 1)
                await asyncio.sleep(min(delay, 30))
            if response.is_error:
                raise RuntimeError(f"Groq returned HTTP {response.status_code}: {response.text[:1000]}")
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)

    async def _store(self, content: str, custom_id: str, kind: str, job_id: str) -> str:
        payload = {
            "content": content,
            "customId": custom_id,
            "containerTags": [MEETING_CONTAINER],
            "metadata": {"source": "jarvis-meeting-agent", "kind": kind, "jobId": job_id},
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{SUPERMEMORY_URL}/v3/documents", json=payload)
            response.raise_for_status()
        return response.json()["id"]

    async def _search(self, query: str, limit: int = 4) -> list[dict[str, str]]:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; JarvisMeetingResearch/0.1)"}
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()
        parser = SearchParser()
        parser.feed(response.text)
        results = [item for item in parser.results if item["url"].startswith("http")]
        trusted = (
            "openai.com", "nvidia.com", "groq.com", "huggingface.co", "runpod.io",
            "modal.com", "together.ai", "fireworks.ai", "aws.amazon.com",
            "cloud.google.com", "microsoft.com",
        )
        results.sort(key=lambda item: 0 if any(domain in urlparse(item["url"]).netloc for domain in trusted) else 1)
        return results[:limit]

    async def _read_page(self, result: dict[str, str]) -> dict[str, str]:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; JarvisMeetingResearch/0.1)"}
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=headers) as client:
                response = await client.get(result["url"])
                response.raise_for_status()
            if "text/html" not in response.headers.get("content-type", ""):
                return result
            parser = TextParser()
            parser.feed(response.text[:1_000_000])
            text = re.sub(r"\s+", " ", " ".join(parser.text))[:2200]
            return {**result, "content": text}
        except Exception as error:
            return {**result, "content": result.get("snippet", ""), "fetchError": str(error)}

    async def _research(self, task: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
        plan = await self._groq_json(
            (
                "You plan bounded web research. Return JSON only with a queries array containing exactly three focused "
                "search queries. Prefer primary sources, official pricing pages, model documentation, and first-party benchmarks."
            ),
            json.dumps({"question": task["researchQuestion"], "task": task["task"]}),
            500,
        )
        queries = [str(query) for query in plan.get("queries", [])][:3]
        result_groups = await asyncio.gather(*(self._search(query) for query in queries))
        unique: dict[str, dict[str, str]] = {}
        for result in [item for group in result_groups for item in group]:
            unique.setdefault(result["url"], result)
        sources = await asyncio.gather(*(self._read_page(item) for item in list(unique.values())[:5]))
        evidence = [
            {
                "sourceId": index + 1,
                "title": source["title"],
                "url": source["url"],
                "text": (source.get("content") or source.get("snippet", ""))[:1800],
            }
            for index, source in enumerate(sources)
        ]
        draft = await self._groq_json(
            (
                "You are Jarvis's background research agent. Use only the supplied web evidence. "
                "Return JSON with title, executiveSummary, conclusion (yes/no/only-if), findings (array), "
                "recommendation, assumptions (array), caveats (array), and citations (array of sourceId integers). "
                "Clearly distinguish building a focused product using third-party models from training a frontier model."
            ),
            json.dumps({"assignment": task, "evidence": evidence}),
            2200,
        )
        self._event(job, "reviewing", "Evidence critic is checking scope, claims, and citations")
        report = await self._groq_json(
            (
                "You are an evidence critic reviewing another research agent. Return a corrected JSON report with exactly "
                "these fields: title, executiveSummary, conclusion, findings, recommendation, assumptions, caveats. "
                "Conclusion must be one of no, only-if, or yes. Use 'no' when the literal goal is infeasible; use 'only-if' "
                "when only a narrower reinterpretation is feasible. Every finding must be an object with point and sourceId, "
                "where sourceId is one integer that exists in the evidence. Remove unsupported numeric claims and do not "
                "equate wrapping third-party models with training or operating a frontier-model competitor."
            ),
            json.dumps({"assignment": task, "draft": draft, "evidence": evidence}),
            2200,
        )
        valid_ids = {item["sourceId"] for item in evidence}
        findings = []
        for finding in report.get("findings", []):
            source_id = finding.get("sourceId") if isinstance(finding, dict) else None
            if source_id in valid_ids:
                findings.append(finding)
        report["findings"] = findings
        report["citations"] = sorted({item["sourceId"] for item in findings})
        report["sources"] = [{"sourceId": item["sourceId"], "title": item["title"], "url": item["url"]} for item in evidence]
        report["queries"] = queries
        return report

    async def _run(self, job_id: str, fixture_path: Path) -> None:
        job = self.jobs[job_id]
        job["status"] = "running"
        started = perf_counter()
        try:
            meeting = json.loads(fixture_path.read_text(encoding="utf-8"))
            self._event(job, "extracting", "Extracting decisions and user-owned assignments")
            extraction = await self._groq_json(
                (
                    "Analyze a meeting transcript. Return JSON only with summary, decisions (array), and actionItems (array). "
                    "Only include commitments owned by the named user. Each action item must have owner, task, due, "
                    "evidenceQuote, evidenceTimestamp, requiresResearch, and researchQuestion. Do not convert chatter, "
                    "other people's work, or ambiguous suggestions into user assignments."
                ),
                json.dumps(meeting),
            )
            actions = extraction.get("actionItems", [])
            self._event(job, "storing_meeting", f"Storing meeting and {len(actions)} extracted action item(s)")
            transcript = "\n".join(f"[{s['timestamp']}] {s['speaker']}: {s['text']}" for s in meeting["segments"])
            meeting_doc = await self._store(
                f"Meeting: {meeting['title']}\nSummary: {extraction.get('summary', '')}\nDecisions: {json.dumps(extraction.get('decisions', []))}\nTranscript:\n{transcript}",
                f"meeting-{job_id}", "meeting", job_id,
            )
            action_docs = []
            reports = []
            for index, action in enumerate(actions, 1):
                action_docs.append(await self._store(json.dumps(action), f"meeting-action-{job_id}-{index}", "action-item", job_id))
                if action.get("requiresResearch"):
                    self._event(job, "researching", f"Research agent started: {action.get('researchQuestion')}")
                    report = await self._research(action, job)
                    reports.append(report)
                    await self._store(json.dumps(report), f"meeting-report-{job_id}-{index}", "research-report", job_id)
            self._event(job, "completed", f"Completed {len(reports)} background research report(s)")
            job["status"] = "completed"
            job["result"] = {
                "meeting": meeting,
                "extraction": extraction,
                "reports": reports,
                "supermemory": {"container": MEETING_CONTAINER, "meetingDocumentId": meeting_doc, "actionDocumentIds": action_docs},
                "elapsedSeconds": round(perf_counter() - started, 2),
            }
        except Exception as error:
            job["status"] = "failed"
            job["error"] = f"{type(error).__name__}: {error}"
            self._event(job, "failed", job["error"])


meeting_agent = MeetingAgent()
