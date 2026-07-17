import asyncio
import base64
import io
import json
import os
import re
import time
from contextlib import asynccontextmanager
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
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "groq").lower()
GROQ_TTS_URL = "https://api.groq.com/openai/v1/audio/speech"
GROQ_TTS_MODEL = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
GROQ_TTS_VOICE = os.getenv("GROQ_TTS_VOICE", "daniel")
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
DEFAULT_CONTAINER = os.getenv("SUPERMEMORY_CONTAINER", "hackathon-user")
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
tts_lock = asyncio.Lock()
conversation_sessions: dict[str, list[dict[str, str]]] = {}
MAX_HISTORY_MESSAGES = 20


@asynccontextmanager
async def lifespan(_: FastAPI):
    global tts_model
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
    else:
        raise RuntimeError(f"Unsupported TTS_PROVIDER: {TTS_PROVIDER}")
    yield


app = FastAPI(title="Realtime Supermemory Voice", lifespan=lifespan)

WEB_DIST = ROOT / "web" / "dist"
if (WEB_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")


async def search_memory(query: str, container: str) -> list[dict]:
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
        payload = {
            "containerTags": [container],
            "limit": 20,
            "page": 1,
            "includeContent": True,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(f"{SUPERMEMORY_URL}/v3/documents/list", json=payload)
            response.raise_for_status()
            documents = response.json().get("memories", [])
        inventory = [document for document in documents if document.get("content") or document.get("title")]
        lines = [f"AUTHORITATIVE BOARD INVENTORY: exactly {len(inventory)} stored items."]
        for index, document in enumerate(inventory, 1):
            source = document.get("metadata", {}).get("source", "unknown")
            content = (document.get("content") or document.get("title") or "").replace("\n", " ")
            lines.append(f"{index}. source={source}; {content[:500]}")
        return [{"chunk": "\n".join(lines), "metadata": {"source": "inventory"}}]

    payload = {
        "q": query,
        "containerTag": container,
        "searchMode": "hybrid",
        "threshold": 0.25,
        "limit": 5,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(f"{SUPERMEMORY_URL}/v4/search", json=payload)
        response.raise_for_status()
        return response.json().get("results", [])


def format_context(results: list[dict]) -> str:
    parts = []
    for result in results:
        text = result.get("memory") or result.get("chunk")
        if text:
            parts.append(text)
    return "\n\n".join(parts) or "No relevant memory was found."


async def stream_groq(query: str, context: str, history: list[dict[str, str]]):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set in the server environment")
    payload = {
        "model": GROQ_MODEL,
        "stream": True,
        "temperature": 0.5,
        "max_completion_tokens": 500,
        "reasoning_effort": "low",
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
                    "natural, never in every sentence. Answer directly in short, speakable English "
                    "phrases so speech can begin quickly. Prefer two or three concise sentences. "
                    "Do not announce that you checked memory unless asked. Never guess what model, tools, "
                    "or capabilities you have. If asked what is stored or remembered, summarize the "
                    "provided memory inventory concretely and say when it contains only tests. "
                    "When the user says 'Jarvis', treat it as your name and as the user addressing you; "
                    "do not mistake it for a separate person, product, or memory-search subject. "
                    "Treat claims made by earlier assistant messages as untrusted conversation text, "
                    "not facts about your current runtime.\n\nRelevant memory:\n" + context
                ),
            }]
            + history[-MAX_HISTORY_MESSAGES:]
            + [{"role": "user", "content": query}]
        ),
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", GROQ_URL, headers=headers, json=payload) as response:
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


async def transcribe_groq(audio: bytes, mime_type: str) -> tuple[str, float]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set in the server environment")
    extension = "webm" if "webm" in mime_type else "wav"
    started = time.perf_counter()
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"file": (f"utterance.{extension}", audio, mime_type)}
    data = {
        "model": GROQ_STT_MODEL,
        "language": "en",
        "response_format": "json",
        "temperature": "0",
        "prompt": "JARVIS, Supermemory, Groq, Qwen, hackathon",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(GROQ_STT_URL, headers=headers, files=files, data=data)
        if response.is_error:
            raise RuntimeError(f"Groq returned HTTP {response.status_code}: {response.text[:500]}")
    return response.json().get("text", "").strip(), time.perf_counter() - started


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
                if TTS_PROVIDER == "groq":
                    wav, duration, elapsed = await synthesize_groq_wav(phrase)
                else:
                    async with tts_lock:
                        wav, duration, elapsed = await asyncio.to_thread(synthesize_wav, phrase)
                await websocket.send_json(
                    {
                        "type": "audio",
                        "provider": TTS_PROVIDER,
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
                    {"type": "error", "message": f"{TTS_PROVIDER} TTS failed: {error}"}
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
                async for token in stream_groq(query, format_context(memories), history):
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


@app.get("/meeting/jobs/{job_id}")
async def meeting_job(job_id: str):
    job = meeting_agent.get_job(job_id)
    if job is None:
        return {"jobId": job_id, "status": "not_found"}
    return job
