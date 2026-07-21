import asyncio
import base64
import io
import json
import os
import re
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import mlx.core as mx
import numpy as np
import soundfile as sf
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from mlx_audio.tts.utils import load_model

from meeting_agent import meeting_agent


ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / os.getenv(
    "QWEN_TTS_MODEL",
    ".models/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit",
)
SUPERMEMORY_URL = os.getenv("SUPERMEMORY_URL", "http://127.0.0.1:6767")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low")
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "groq").lower()
GROQ_TTS_URL = "https://api.groq.com/openai/v1/audio/speech"
GROQ_TTS_MODEL = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
GROQ_TTS_VOICE = os.getenv("GROQ_TTS_VOICE", "daniel")
ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech"
ELEVENLABS_TTS_MODEL = os.getenv("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5")
ELEVENLABS_TTS_VOICE_ID = os.getenv("ELEVENLABS_TTS_VOICE_ID", "onwK4e9ZLuTAKqWW03F9")
KOKORO_MODEL_PATH = ROOT / os.getenv("KOKORO_MODEL", ".models/Kokoro-82M-4bit")
KOKORO_VOICE = os.getenv("KOKORO_VOICE", "bm_daniel")
KOKORO_SPEED = float(os.getenv("KOKORO_SPEED", "1.30"))
MACOS_TTS_VOICE = os.getenv("MACOS_TTS_VOICE", "Daniel")
MACOS_TTS_RATE = os.getenv("MACOS_TTS_RATE", "190")
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3")
GROQ_STT_FALLBACK_MODEL = os.getenv("GROQ_STT_FALLBACK_MODEL", "whisper-large-v3-turbo")
DEFAULT_CONTAINER = os.getenv("SUPERMEMORY_CONTAINER", "hackathon-user")
MEETING_CONTAINER = os.getenv("MEETING_CONTAINER", "jarvis-meeting-demo")
SPEAKER = os.getenv("QWEN_TTS_SPEAKER", "Ryan")
VOICE_INSTRUCTION = os.getenv(
    "QWEN_TTS_INSTRUCTION",
    (
        "A refined British-style personal butler. Use a calm lower register, measured pacing, "
        "precise diction, restrained confidence, and subtle dry warmth. Sound intelligent and "
        "protective, never theatrical, breathy, or overly emotional."
    ),
)

tts_model = None
kokoro_model = None
tts_lock = asyncio.Lock()
conversation_sessions: dict[str, list[dict[str, str]]] = {}
pending_memory_deletions: dict[str, dict[str, str]] = {}
meeting_sessions: dict[str, dict] = {}
MAX_HISTORY_MESSAGES = 10
MAX_RECALL_CHARACTERS = 4200


@asynccontextmanager
async def lifespan(_: FastAPI):
    global tts_model, kokoro_model
    if TTS_PROVIDER == "qwen":
        if not MODEL_PATH.exists():
            raise RuntimeError(f"MLX model not found: {MODEL_PATH}")
        started = time.perf_counter()
        tts_model = await asyncio.to_thread(load_model, str(MODEL_PATH))
        print(f"Qwen3-TTS ready on {mx.default_device()} in {time.perf_counter() - started:.1f}s")
    elif TTS_PROVIDER == "groq":
        if not os.getenv("GROQ_API_KEY"):
            raise RuntimeError("GROQ_API_KEY is required for Groq TTS")
        print(f"Groq TTS ready: {GROQ_TTS_MODEL} / {GROQ_TTS_VOICE}")
    elif TTS_PROVIDER == "elevenlabs":
        if not os.getenv("ELEVENLABS_API_KEY"):
            raise RuntimeError("ELEVENLABS_API_KEY is required for ElevenLabs TTS")
        print(f"ElevenLabs TTS ready: {ELEVENLABS_TTS_MODEL} / {ELEVENLABS_TTS_VOICE_ID}")
    elif TTS_PROVIDER == "kokoro":
        if not KOKORO_MODEL_PATH.is_dir():
            raise RuntimeError(f"Kokoro model not found: {KOKORO_MODEL_PATH}")
        print(f"Kokoro selected as primary TTS: {KOKORO_VOICE}")
    else:
        raise RuntimeError(f"Unsupported TTS_PROVIDER: {TTS_PROVIDER}")
    if KOKORO_MODEL_PATH.is_dir():
        started = time.perf_counter()
        kokoro_model = await asyncio.to_thread(load_model, str(KOKORO_MODEL_PATH))
        print(
            f"Kokoro fallback ready: {KOKORO_VOICE} in "
            f"{time.perf_counter() - started:.1f}s"
        )
    yield


app = FastAPI(title="Realtime Supermemory Voice", lifespan=lifespan)

WEB_DIST = ROOT / "web" / "dist"
if (WEB_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")


async def search_memory(query: str, container: str) -> list[dict]:
    containers = list(dict.fromkeys([container, MEETING_CONTAINER]))
    normalized = query.lower()
    inventory_request = any(
        phrase in normalized
        for phrase in (
            "what's in my super memory",
            "what is in my super memory",
            "what's on my super memory",
            "what is on my super memory",
            "what do you remember",
            "memory board",
        )
    )
    if inventory_request:
        async with httpx.AsyncClient(timeout=15) as client:
            async def list_all(path: str, result_key: str, tag: str) -> list[dict]:
                page = 1
                items: list[dict] = []
                while True:
                    response = await client.post(
                        f"{SUPERMEMORY_URL}{path}",
                        json={"containerTags": [tag], "limit": 100, "page": page},
                    )
                    response.raise_for_status()
                    body = response.json()
                    items.extend(body.get(result_key, []))
                    if page >= int(body.get("pagination", {}).get("totalPages") or 1):
                        return items
                    page += 1

            batches = await asyncio.gather(
                *(list_all("/v3/documents/list", "memories", tag) for tag in containers),
                *(list_all("/v4/memories/list", "memoryEntries", tag) for tag in containers),
            )

        document_batches = batches[: len(containers)]
        memory_batches = batches[len(containers) :]
        documents = {
            str(item["id"]): item
            for batch in document_batches
            for item in batch
            if item.get("id")
        }
        memories = {
            str(item["id"]): item
            for batch in memory_batches
            for item in batch
            if item.get("id") and not item.get("isForgotten")
        }
        category_counts: dict[str, int] = {}
        for document in documents.values():
            kind = str(document.get("metadata", {}).get("kind") or "conversation")
            category_counts[kind] = category_counts.get(kind, 0) + 1
        categories = ", ".join(
            f"{kind}={count}" for kind, count in sorted(category_counts.items())
        )
        references = ", ".join(
            f"{tag}={len(batch)}" for tag, batch in zip(containers, document_batches)
        )
        lines = [
            "AUTHORITATIVE SUPERMEMORY INVENTORY (complete and paginated; never infer totals):",
            f"structuredMemories={len(memories)}; uniqueDocuments={len(documents)}; "
            f"documentReferences={sum(len(batch) for batch in document_batches)}",
            f"documentCategories: {categories}",
            f"containerDocumentReferences: {references}",
            "STRUCTURED MEMORIES:",
        ]
        lines.extend(
            f"- {str(memory.get('memory') or '').replace(chr(10), ' ')[:260]}"
            for memory in memories.values()
            if memory.get("memory")
        )
        important_documents = sorted(
            documents.values(),
            key=lambda item: (
                item.get("metadata", {}).get("kind") in {None, "conversation"},
                str(item.get("createdAt") or ""),
            ),
        )
        lines.append("NON-CONVERSATION AND RECENT DOCUMENTS:")
        lines.extend(
            f"- kind={item.get('metadata', {}).get('kind') or 'conversation'}; "
            f"title={str(item.get('title') or '').replace(chr(10), ' ')[:180]}"
            for item in important_documents[:24]
        )
        return [{"chunk": "\n".join(lines), "metadata": {"source": "inventory"}}]

    payloads = [
        {"q": query, "containerTag": tag, "searchMode": "hybrid", "threshold": 0.25, "limit": 5}
        for tag in containers
    ]
    async with httpx.AsyncClient(timeout=15) as client:
        responses = await asyncio.gather(
            *(client.post(f"{SUPERMEMORY_URL}/v4/search", json=payload) for payload in payloads)
        )
        results = []
        seen = set()
        for response in responses:
            response.raise_for_status()
            for result in response.json().get("results", []):
                key = result.get("id") or result.get("documentId") or result.get("chunk")
                if key not in seen:
                    seen.add(key)
                    results.append(result)
        return sorted(
            results,
            key=lambda item: float(item.get("similarity") or item.get("score") or 0),
            reverse=True,
        )[:5]


def format_context(results: list[dict]) -> str:
    parts = []
    for result in results:
        text = result.get("memory") or result.get("chunk")
        if text:
            parts.append(text[:1400])
    return ("\n\n".join(parts)[:MAX_RECALL_CHARACTERS] or "No relevant memory was found.")


async def handle_memory_mutation(query: str, container: str, session_id: str) -> str | None:
    """Execute explicit memory writes and stage destructive actions for confirmation."""
    normalized = query.strip().lower()
    if normalized in {"confirm delete", "confirm deletion", "yes, delete it", "delete it"}:
        pending = pending_memory_deletions.pop(session_id, None)
        if not pending:
            return "MEMORY ACTION: No deletion was pending; nothing was deleted."
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.delete(
                f"{SUPERMEMORY_URL}/v3/documents/{pending['documentId']}"
            )
            response.raise_for_status()
        return f"MEMORY ACTION COMPLETED: Deleted the confirmed item: {pending['label']}."

    delete_match = re.match(r"^(?:jarvis[, ]+)?(?:delete|remove|forget)\s+(.+)$", query, re.I)
    if delete_match:
        target = delete_match.group(1).strip()
        results = await search_memory(target, container)
        candidate = next(
            (
                item for item in results
                if item.get("documentId") or item.get("metadata", {}).get("documentId")
            ),
            None,
        )
        if not candidate:
            return f"MEMORY ACTION: No deletable Supermemory document matched '{target}'."
        document_id = str(
            candidate.get("documentId") or candidate.get("metadata", {}).get("documentId")
        )
        label = str(candidate.get("title") or candidate.get("chunk") or target)[:160]
        pending_memory_deletions[session_id] = {"documentId": document_id, "label": label}
        return (
            "MEMORY ACTION REQUIRES CONFIRMATION: A matching item was found but not deleted. "
            f"Candidate: {label}. Ask the user to say 'confirm delete'."
        )

    add_match = re.match(
        r"^(?:jarvis[, ]+)?(?:remember|save|add to (?:my )?(?:supermemory|memory)(?: board)?)\s+(?:that\s+)?(.+)$",
        query,
        re.I,
    )
    if add_match:
        content = add_match.group(1).strip()
        payload = {
            "content": content,
            "containerTag": container,
            "metadata": {"kind": "user-memory", "source": "jarvis-voice"},
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(f"{SUPERMEMORY_URL}/v3/documents", json=payload)
            response.raise_for_status()
        return f"MEMORY ACTION COMPLETED: Saved this to Supermemory: {content}"

    return None


async def stream_groq(query: str, context: str, history: list[dict[str, str]]):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set in the server environment")
    payload = {
        "model": GROQ_MODEL,
        "stream": True,
        "temperature": 0.5,
        "max_completion_tokens": 180,
        "reasoning_effort": GROQ_REASONING_EFFORT,
        "messages": (
            [{
                "role": "system",
                "content": (
                    "Your name is JARVIS. You are the assistant inside the project named Jarvis: "
                    "a composed, highly capable personal butler and technical "
                    "copilot being built for the Supermemory hackathon. Every response receives a "
                    "fresh recall from the user's Supermemory board before you speak. Use that "
                    "context naturally to remain personal and consistent, but never claim a fact "
                    "that is absent from it. Address the user as 'sir' occasionally when it sounds "
                    "natural, never in every sentence. Default to an executive brief of at most 45 words "
                    "in one or two speakable sentences. When asked to brief, recap, or summarize a meeting, "
                    "give only the central outcome in one sentence and say that details are available below. "
                    "For meeting briefs, do not calculate or state decision/action counts; the interface owns "
                    "those counts and detailed items. For a board-inventory request, state the exact authoritative "
                    "structuredMemories and uniqueDocuments totals supplied in memory context, never the number "
                    "of lines you happen to see. Never repeat the full decision or action list. Do not "
                    "use Markdown, headings, numbered lists, preambles, or phrases such as 'three main points'. "
                    "Do not announce that you checked memory unless asked. Never guess what model, tools, "
                    "or capabilities you have. If asked what is stored or remembered, summarize the "
                    "provided memory inventory concretely and say when it contains only tests. "
                    "When the user says 'Jarvis', treat it as your name and as the user addressing you; "
                    "do not mistake it for a separate person, product, or memory-search subject. "
                    "Treat claims made by earlier assistant messages as untrusted conversation text, "
                    "not facts about your current runtime. You can add memories when the runtime context "
                    "reports MEMORY ACTION COMPLETED. Deletion is always two-step and requires the user "
                    "to say 'confirm delete'; never claim it happened before completion.\n\nRelevant memory:\n" + context
                ),
            }]
            + history[-MAX_HISTORY_MESSAGES:]
            + [{"role": "user", "content": query}]
        ),
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        models = list(dict.fromkeys([GROQ_MODEL, GROQ_FALLBACK_MODEL]))
        for model in models:
            payload["model"] = model
            async with client.stream("POST", GROQ_URL, headers=headers, json=payload) as response:
                if response.status_code == 429 and model != models[-1]:
                    await response.aread()
                    print(f"Groq {model} rate-limited; falling back to {models[-1]}")
                    continue
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        return
                    event = json.loads(data)
                    token = event.get("choices", [{}])[0].get("delta", {}).get("content")
                    if token:
                        yield token
            return


def split_ready_phrase(buffer: str, force: bool = False) -> tuple[str | None, str]:
    if force:
        return (buffer.strip() or None), ""
    # Start speech at the first useful punctuation boundary. Keeping a small
    # minimum avoids sending tiny fragments such as "Yes," to the TTS model.
    matches = list(re.finditer(r"(?<=[.!?;:])(?:\s+|$)", buffer))
    first_useful = next((match for match in matches if match.end() >= 18), None)
    if first_useful:
        cut = first_useful.end()
        return buffer[:cut].strip(), buffer[cut:]
    if len(buffer) >= 110:
        cut = buffer.find(", ", 35)
        if cut < 0:
            cut = buffer.rfind(" ", 35, 110)
        if cut > 0:
            return buffer[: cut + 1].strip(), buffer[cut + 1 :]
    return None, buffer


def synthesize_wav(text: str) -> tuple[str, float, float]:
    started = time.perf_counter()
    results = list(
        tts_model.generate_custom_voice(
            text=text,
            speaker=SPEAKER,
            language="English",
            instruct=VOICE_INSTRUCTION,
            max_tokens=512,
            verbose=False,
        )
    )
    if not results:
        raise RuntimeError("TTS generated no audio")
    sample_rate = int(results[0].sample_rate)
    audio = np.concatenate([np.asarray(result.audio, dtype=np.float32) for result in results])
    output = io.BytesIO()
    sf.write(output, audio, sample_rate, format="WAV", subtype="PCM_16")
    elapsed = time.perf_counter() - started
    return base64.b64encode(output.getvalue()).decode("ascii"), len(audio) / sample_rate, elapsed


async def synthesize_groq_wav(text: str) -> tuple[str, float, float]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set in the server environment")
    started = time.perf_counter()
    payload = {
        "model": GROQ_TTS_MODEL,
        "voice": GROQ_TTS_VOICE,
        "input": text[:200],
        "response_format": "wav",
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(GROQ_TTS_URL, headers=headers, json=payload)
        if response.is_error:
            raise RuntimeError(f"Groq returned HTTP {response.status_code}: {response.text[:500]}")
    wav_bytes = response.content
    info = sf.info(io.BytesIO(wav_bytes))
    return (
        base64.b64encode(wav_bytes).decode("ascii"),
        float(info.duration),
        time.perf_counter() - started,
    )


async def synthesize_elevenlabs_wav(text: str) -> tuple[str, float, float]:
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set in the server environment")
    started = time.perf_counter()
    url = f"{ELEVENLABS_TTS_URL}/{ELEVENLABS_TTS_VOICE_ID}"
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "text": text[:300],
        "model_id": ELEVENLABS_TTS_MODEL,
        "language_code": "en",
        "voice_settings": {
            "stability": 0.42,
            "similarity_boost": 0.78,
            "style": 0.08,
            "use_speaker_boost": False,
            "speed": 1.12,
        },
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            url, params={"output_format": "mp3_44100_128"}, headers=headers, json=payload
        )
        if response.is_error:
            raise RuntimeError(
                f"ElevenLabs returned HTTP {response.status_code}: {response.text[:500]}"
            )
    audio, sample_rate = sf.read(io.BytesIO(response.content), dtype="float32")
    output = io.BytesIO()
    sf.write(output, audio, sample_rate, format="WAV", subtype="PCM_16")
    return (
        base64.b64encode(output.getvalue()).decode("ascii"),
        len(audio) / int(sample_rate),
        time.perf_counter() - started,
    )


def synthesize_kokoro_wav(text: str) -> tuple[str, float, float]:
    if kokoro_model is None:
        raise RuntimeError("Kokoro fallback model is not loaded")
    started = time.perf_counter()
    voice_path = KOKORO_MODEL_PATH / "voices" / f"{KOKORO_VOICE}.safetensors"
    if not voice_path.is_file():
        raise RuntimeError(f"Kokoro voice not found: {voice_path}")
    chunks = list(
        kokoro_model.generate(
            text=text[:300],
            voice=str(voice_path),
            speed=KOKORO_SPEED,
            lang_code="b",
        )
    )
    if not chunks:
        raise RuntimeError("Kokoro did not generate audio")
    audio = np.concatenate([np.asarray(chunk.audio, dtype=np.float32) for chunk in chunks])
    output = io.BytesIO()
    sf.write(output, audio, kokoro_model.sample_rate, format="WAV", subtype="PCM_16")
    return (
        base64.b64encode(output.getvalue()).decode("ascii"),
        len(audio) / int(kokoro_model.sample_rate),
        time.perf_counter() - started,
    )


async def synthesize_macos_wav(text: str) -> tuple[str, float, float]:
    started = time.perf_counter()
    descriptor, path = tempfile.mkstemp(prefix="jarvis-tts-", suffix=".aiff")
    os.close(descriptor)
    try:
        process = await asyncio.create_subprocess_exec(
            "/usr/bin/say",
            "-v", MACOS_TTS_VOICE,
            "-r", MACOS_TTS_RATE,
            "-o", path,
            text[:300],
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode:
            raise RuntimeError(stderr.decode("utf-8", errors="replace").strip())
        audio, sample_rate = sf.read(path, dtype="float32")
        output = io.BytesIO()
        sf.write(output, audio, sample_rate, format="WAV", subtype="PCM_16")
        duration = len(audio) / int(sample_rate)
        return base64.b64encode(output.getvalue()).decode("ascii"), duration, time.perf_counter() - started
    finally:
        Path(path).unlink(missing_ok=True)


async def transcribe_groq(audio: bytes, mime_type: str) -> tuple[str, float]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set in the server environment")
    extension = "webm" if "webm" in mime_type else "wav"
    started = time.perf_counter()
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"file": (f"utterance.{extension}", audio, mime_type)}
    data = {
        "language": "en",
        "response_format": "json",
        "temperature": "0",
        "prompt": (
            "JARVIS personal assistant meeting. Supermemory, Groq, ElevenLabs, Kokoro, Qwen, "
            "NVIDIA NIM, Nemotron, ScreenCaptureKit, macOS, research agent, hackathon."
        ),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        models = list(dict.fromkeys([GROQ_STT_MODEL, GROQ_STT_FALLBACK_MODEL]))
        for model in models:
            data["model"] = model
            response = await client.post(GROQ_STT_URL, headers=headers, files=files, data=data)
            if response.status_code == 429 and model != models[-1]:
                print(f"Groq STT {model} rate-limited; falling back to {models[-1]}")
                continue
            if response.is_error:
                raise RuntimeError(
                    f"Groq returned HTTP {response.status_code}: {response.text[:500]}"
                )
            break
    return response.json().get("text", "").strip(), time.perf_counter() - started


def public_meeting_session(session: dict) -> dict:
    return {key: value for key, value in session.items() if key != "lock"}


def normalize_meeting_summary(summary: dict, session: dict, transcript: str) -> dict:
    summary = summary if isinstance(summary, dict) else {}
    attendee_text = " ".join(
        segment["text"] for segment in session["segments"]
        if segment.get("source") != "Dev" and segment.get("text")
    )
    fallback = attendee_text[:420].strip() or transcript[:420].strip()
    if len(attendee_text) > 420:
        fallback = fallback.rsplit(" ", 1)[0] + "…"
    return {
        "title": str(summary.get("title") or session.get("title") or "Meeting brief"),
        "summary": str(summary.get("summary") or fallback or "The meeting was captured, but no spoken summary was available."),
        "participants": summary.get("participants") if isinstance(summary.get("participants"), list) else [],
        "decisions": summary.get("decisions") if isinstance(summary.get("decisions"), list) else [],
        "actionItems": summary.get("actionItems") if isinstance(summary.get("actionItems"), list) else [],
        "commandPlan": summary.get("commandPlan") if isinstance(summary.get("commandPlan"), list) else [],
        "openQuestions": summary.get("openQuestions") if isinstance(summary.get("openQuestions"), list) else [],
        "keyMoments": summary.get("keyMoments") if isinstance(summary.get("keyMoments"), list) else [],
    }


async def summarize_meeting_session(session: dict) -> dict:
    transcript = "\n".join(
        f"[{segment['timestamp']}] {segment['source']}: {segment['text']}"
        for segment in session["segments"]
    )
    if not transcript.strip():
        raise ValueError("No speech was captured for this meeting")
    memory_context = await meeting_agent._recall(
        f"{session['title']} {transcript[:2500]}"
    )
    meeting_context = {
        "startedAt": session["createdAt"],
        "endedAt": session.get("endedAt"),
        "durationSeconds": session.get("durationSeconds"),
        "timezone": session.get("timezone"),
        "locale": session.get("locale"),
        "platform": session.get("platform"),
        "captureSurface": session.get("captureSurface"),
        "sourceLabel": session.get("sourceLabel"),
    }
    summary = await meeting_agent._model_json(
        (
            "You are JARVIS Meeting Analyst. Return JSON only with exactly these keys: title, summary, "
            "participants, decisions, actionItems, commandPlan, openQuestions, and keyMoments. participants is an array "
            "of names or speaker labels. decisions and openQuestions are arrays of strings. actionItems is "
            "an array of objects with owner, task, and dueDate. keyMoments is an array of objects with "
            "timestamp and note. commandPlan is an array of objects with command, purpose, and "
            "requiresApproval. When an attendee asks the user to perform a local terminal task, provide "
            "safe, copyable commands that accomplish only the explicitly requested preparation. For an "
            "empty Git repository this may include mkdir -p, cd, and git init. Never execute commands. "
            "Never include credentials, installs, destructive commands, remote creation, commits, or pushes. "
            "Never invent a person, decision, deadline, or action. Use null when an "
            "owner or due date was not stated. Keep the summary concise and useful after the meeting."
        ),
        json.dumps(
            {
                "meetingTitle": session["title"],
                "meetingContext": meeting_context,
                "transcript": transcript,
                "freshSupermemoryRecall": memory_context,
            }
        ),
        2200,
    )
    summary = normalize_meeting_summary(summary, session, transcript)
    document_id = await meeting_agent._store(
        json.dumps({"meetingContext": meeting_context, "summary": summary, "transcript": transcript}),
        f"captured-meeting-{session['sessionId']}",
        "captured-meeting",
        session["sessionId"],
        [DEFAULT_CONTAINER, MEETING_CONTAINER],
    )
    return {"meetingContext": meeting_context, "summary": summary, "transcript": transcript, "supermemoryDocumentId": document_id}


async def remember_exchange(
    query: str, answer: str, container: str, conversation_id: str
) -> None:
    payload = {
        "conversationId": conversation_id,
        "containerTags": [container],
        "messages": [
            {"role": "user", "content": query},
            {"role": "assistant", "content": answer},
        ],
        "metadata": {"source": "realtime-voice"},
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(f"{SUPERMEMORY_URL}/v4/conversations", json=payload)
        response.raise_for_status()


async def tts_worker(websocket: WebSocket, queue: asyncio.Queue, request_started: float):
    first_audio = True
    while True:
        phrase = await queue.get()
        if phrase is None:
            queue.task_done()
            return
        try:
            try:
                provider = TTS_PROVIDER
                if TTS_PROVIDER == "elevenlabs":
                    try:
                        wav, duration, elapsed = await synthesize_elevenlabs_wav(phrase)
                    except Exception as elevenlabs_error:
                        print(f"ElevenLabs TTS unavailable; trying Kokoro: {elevenlabs_error}")
                        try:
                            async with tts_lock:
                                wav, duration, elapsed = await asyncio.to_thread(
                                    synthesize_kokoro_wav, phrase
                                )
                            provider = "kokoro"
                        except Exception as kokoro_error:
                            print(f"Kokoro unavailable; trying Groq: {kokoro_error}")
                            try:
                                wav, duration, elapsed = await synthesize_groq_wav(phrase)
                                provider = "groq"
                            except Exception as groq_error:
                                print(
                                    f"Groq TTS unavailable; using macOS {MACOS_TTS_VOICE}: "
                                    f"{groq_error}"
                                )
                                wav, duration, elapsed = await synthesize_macos_wav(phrase)
                                provider = "macos"
                elif TTS_PROVIDER == "groq":
                    try:
                        wav, duration, elapsed = await synthesize_groq_wav(phrase)
                    except Exception as groq_error:
                        print(f"Groq TTS unavailable; using macOS {MACOS_TTS_VOICE}: {groq_error}")
                        wav, duration, elapsed = await synthesize_macos_wav(phrase)
                        provider = "macos"
                elif TTS_PROVIDER == "kokoro":
                    async with tts_lock:
                        wav, duration, elapsed = await asyncio.to_thread(
                            synthesize_kokoro_wav, phrase
                        )
                else:
                    async with tts_lock:
                        wav, duration, elapsed = await asyncio.to_thread(synthesize_wav, phrase)
                await websocket.send_json(
                    {
                        "type": "audio",
                        "provider": provider,
                        "text": phrase,
                        "wav": wav,
                        "duration": duration,
                        "generationSeconds": elapsed,
                        "readySeconds": time.perf_counter() - request_started,
                    }
                )
                if first_audio:
                    first_audio = False
            except Exception as error:
                await websocket.send_json(
                    {"type": "warning", "message": f"Voice unavailable; text continued: {error}"}
                )
        finally:
            queue.task_done()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connection_session_id = str(uuid4())
    try:
        while True:
            request = await websocket.receive_json()
            if request.get("type") != "query":
                continue
            query = str(request.get("text", "")).strip()
            container = str(request.get("containerTag") or DEFAULT_CONTAINER)
            session_id = str(request.get("sessionId") or connection_session_id)
            history = conversation_sessions.setdefault(session_id, [])
            if not query:
                continue

            started = time.perf_counter()
            await websocket.send_json({"type": "status", "message": "Recalling memory…"})
            try:
                memories = await search_memory(query, container)
                mutation_context = await handle_memory_mutation(query, container, session_id)
            except Exception as error:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Supermemory recall failed, so JARVIS will not answer: {error}",
                    }
                )
                continue

            await websocket.send_json(
                {"type": "memory", "count": len(memories), "latency": time.perf_counter() - started}
            )
            queue: asyncio.Queue = asyncio.Queue()
            worker = asyncio.create_task(tts_worker(websocket, queue, started))
            answer = ""
            phrase_buffer = ""
            first_token_at = None
            try:
                await websocket.send_json(
                    {"type": "metric", "name": "historyMessages", "count": len(history)}
                )
                context = format_context(memories)
                if mutation_context:
                    context = f"{mutation_context}\n\n{context}"
                async for token in stream_groq(query, context, history):
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                        await websocket.send_json(
                            {"type": "metric", "name": "firstToken", "seconds": first_token_at - started}
                        )
                    answer += token
                    phrase_buffer += token
                    await websocket.send_json({"type": "token", "text": token})
                    phrase, phrase_buffer = split_ready_phrase(phrase_buffer)
                    if phrase:
                        await queue.put(phrase)

                phrase, _ = split_ready_phrase(phrase_buffer, force=True)
                if phrase:
                    await queue.put(phrase)
                await queue.put(None)
                await queue.join()
                await worker
                await websocket.send_json(
                    {"type": "done", "answer": answer, "seconds": time.perf_counter() - started}
                )
                history.extend(
                    [
                        {"role": "user", "content": query},
                        {"role": "assistant", "content": answer},
                    ]
                )
                if len(history) > MAX_HISTORY_MESSAGES:
                    del history[:-MAX_HISTORY_MESSAGES]
                asyncio.create_task(
                    remember_exchange(query, answer, container, session_id)
                )
            except Exception as error:
                worker.cancel()
                await websocket.send_json({"type": "error", "message": str(error)})
    except WebSocketDisconnect:
        return


@app.websocket("/listen")
async def listen_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            request = await websocket.receive_json()
            if request.get("type") != "transcribe":
                continue
            try:
                audio = base64.b64decode(request.get("audio", ""), validate=True)
                if not audio:
                    raise ValueError("empty audio")
                text, elapsed = await transcribe_groq(
                    audio, str(request.get("mimeType") or "audio/webm")
                )
                await websocket.send_json(
                    {"type": "transcript", "text": text, "seconds": elapsed}
                )
            except Exception as error:
                await websocket.send_json(
                    {"type": "transcription_error", "message": str(error)}
                )
    except WebSocketDisconnect:
        return


@app.get("/")
async def index():
    web_index = WEB_DIST / "index.html"
    if web_index.is_file():
        return HTMLResponse(web_index.read_text())
    return HTMLResponse((ROOT / "realtime_voice.html").read_text())


@app.post("/meeting/simulate")
async def simulate_meeting(request: dict):
    return meeting_agent.create_job(str(request.get("fixture") or "fixtures/dummy_meeting.json"))


@app.post("/meetings/sessions")
async def create_meeting_session(request: dict):
    session_id = str(uuid4())
    session = {
        "sessionId": session_id,
        "title": str(request.get("title") or "Captured meeting"),
        "status": "recording",
        "capture": {
            "screen": bool(request.get("screen", True)),
            "systemAudio": bool(request.get("systemAudio", False)),
            "microphone": bool(request.get("microphone", True)),
        },
        "createdAt": str(request.get("startedAt") or datetime.now(timezone.utc).isoformat()),
        "serverCreatedAt": datetime.now(timezone.utc).isoformat(),
        "timezone": str(request.get("timezone") or "UTC"),
        "locale": str(request.get("locale") or "unknown"),
        "platform": str(request.get("platform") or "Unknown meeting platform"),
        "captureSurface": str(request.get("captureSurface") or "unknown"),
        "sourceLabel": str(request.get("sourceLabel") or "Shared screen")[:240],
        "durationSeconds": None,
        "endedAt": None,
        "segments": [],
        "result": None,
        "error": None,
        "lock": asyncio.Lock(),
    }
    meeting_sessions[session_id] = session
    return public_meeting_session(session)


@app.post("/meetings/sessions/{session_id}/segments")
async def add_meeting_segment(session_id: str, request: dict):
    session = meeting_sessions.get(session_id)
    if session is None:
        return {"error": "Meeting session not found"}
    if session["status"] != "recording":
        return {"error": f"Meeting is {session['status']}"}
    try:
        audio = base64.b64decode(str(request.get("audio") or ""), validate=True)
        if len(audio) < 1000:
            raise ValueError("Audio segment is empty or too small")
        async with session["lock"]:
            text, elapsed = await transcribe_groq(
                audio, str(request.get("mimeType") or "audio/webm")
            )
            if text:
                session["segments"].append(
                    {
                        "id": str(uuid4()),
                        "timestamp": str(request.get("timestamp") or "00:00"),
                        "source": str(request.get("source") or "Meeting audio"),
                        "text": text,
                        "transcriptionSeconds": round(elapsed, 2),
                    }
                )
        return {"text": text, "segments": len(session["segments"]), "seconds": elapsed}
    except Exception as error:
        return {"error": str(error)}


@app.post("/meetings/sessions/{session_id}/transcript")
async def add_meeting_transcript(session_id: str, request: dict):
    session = meeting_sessions.get(session_id)
    if session is None:
        return {"error": "Meeting session not found"}
    if session["status"] != "recording":
        return {"error": f"Meeting is {session['status']}"}
    text = str(request.get("text") or "").strip()
    if not text:
        return {"error": "Transcript text is empty"}
    session["segments"].append(
        {
            "id": str(uuid4()),
            "timestamp": str(request.get("timestamp") or "00:00"),
            "source": str(request.get("source") or "Meeting attendee"),
            "text": text,
            "transcriptionSeconds": 0,
        }
    )
    return {"text": text, "segments": len(session["segments"])}


@app.post("/meetings/sessions/{session_id}/finish")
async def finish_meeting_session(session_id: str):
    session = meeting_sessions.get(session_id)
    if session is None:
        return {"error": "Meeting session not found"}
    if session["status"] == "completed":
        return public_meeting_session(session)
    session["status"] = "summarizing"
    session["endedAt"] = datetime.now(timezone.utc).isoformat()
    try:
        start = datetime.fromisoformat(session["createdAt"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(session["endedAt"].replace("Z", "+00:00"))
        session["durationSeconds"] = max(0, round((end - start).total_seconds()))
    except ValueError:
        session["durationSeconds"] = None
    try:
        async with session["lock"]:
            session["result"] = await summarize_meeting_session(session)
        session["status"] = "completed"
    except Exception as error:
        session["status"] = "failed"
        session["error"] = str(error)
    return public_meeting_session(session)


@app.get("/meetings/sessions")
async def list_meeting_sessions(limit: int = 10):
    sessions = sorted(meeting_sessions.values(), key=lambda item: item["createdAt"], reverse=True)
    return {"sessions": [public_meeting_session(item) for item in sessions[:max(1, min(limit, 50))]]}


@app.get("/meetings/sessions/{session_id}")
async def get_meeting_session(session_id: str):
    session = meeting_sessions.get(session_id)
    return public_meeting_session(session) if session else {"error": "Meeting session not found"}


@app.get("/meeting/jobs/{job_id}")
async def meeting_job(job_id: str):
    job = meeting_agent.get_job(job_id)
    if job is None:
        return {"jobId": job_id, "status": "not_found"}
    return job


@app.delete("/meeting/jobs/{job_id}")
async def delete_meeting_job(job_id: str):
    return {"deleted": meeting_agent.delete_job(job_id), "jobId": job_id}


@app.post("/research/jobs")
async def create_research_job(request: dict):
    return meeting_agent.create_research_job(
        str(request.get("question") or ""), str(request.get("context") or "")
    )


@app.get("/research/jobs")
async def list_research_jobs(limit: int = 10):
    return {"jobs": meeting_agent.list_jobs(limit)}


@app.get("/research/jobs/{job_id}")
async def research_job(job_id: str):
    job = meeting_agent.get_job(job_id)
    if job is None:
        return {"jobId": job_id, "status": "not_found"}
    return job


@app.get("/memory/overview")
async def memory_overview():
    """Return a compact, authoritative board summary for the dashboard."""
    containers = list(dict.fromkeys([DEFAULT_CONTAINER, MEETING_CONTAINER]))
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            async def list_all(path: str, key: str, tag: str) -> list[dict]:
                page, items = 1, []
                while True:
                    response = await client.post(
                        f"{SUPERMEMORY_URL}{path}",
                        json={"containerTags": [tag], "limit": 100, "page": page},
                    )
                    response.raise_for_status()
                    body = response.json()
                    items.extend(body.get(key, []))
                    if page >= int(body.get("pagination", {}).get("totalPages") or 1):
                        return items
                    page += 1
            batches = await asyncio.gather(
                *(list_all("/v3/documents/list", "memories", tag) for tag in containers),
                *(list_all("/v4/memories/list", "memoryEntries", tag) for tag in containers),
            )
        document_batches = batches[:len(containers)]
        memory_batches = batches[len(containers):]
        documents = {str(item["id"]): item for batch in document_batches for item in batch if item.get("id")}
        memories = {str(item["id"]): item for batch in memory_batches for item in batch if item.get("id") and not item.get("isForgotten")}
        categories: dict[str, int] = {}
        for item in documents.values():
            kind = str(item.get("metadata", {}).get("kind") or "conversation")
            categories[kind] = categories.get(kind, 0) + 1
        recent = sorted(documents.values(), key=lambda item: str(item.get("createdAt") or ""), reverse=True)[:3]
        return {
            "connected": True,
            "structuredMemories": len(memories),
            "uniqueDocuments": len(documents),
            "categories": [{"name": name.replace("-", " "), "count": count} for name, count in sorted(categories.items(), key=lambda pair: pair[1], reverse=True)[:4]],
            "recent": [{"id": item.get("id"), "title": str(item.get("title") or item.get("metadata", {}).get("kind") or "Memory")[:120], "createdAt": item.get("createdAt")} for item in recent],
        }
    except Exception as error:
        return {"connected": False, "error": str(error)}
