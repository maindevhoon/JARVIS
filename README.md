# JARVIS

JARVIS is a local-first personal AI assistant that turns meetings into durable memory and follow-up work. It captures user-authorized screen, system audio, and microphone input; produces concise meeting briefs; stores context in Supermemory Local; and runs evidence-backed research jobs in the background.

## What it does

- Always-listening voice input with push-to-talk, mute, adaptive noise filtering, and duplicate protection
- Fresh Supermemory recall before every answer with conversational continuity
- Meeting capture with separate `Dev` and `Meeting attendees` transcripts
- Meeting date, time, timezone, duration, capture surface, and platform context
- Summaries, decisions, action items, open questions, and safe command plans
- Background research with evidence review, sources, and persisted reports
- Streaming LLM responses and low-latency TTS with provider fallbacks
- A compact dashboard for memory status, active agents, and current briefs

## Architecture

```text
React dashboard (5173)
        |
FastAPI + WebSockets (8787)
   |        |         |
Groq     TTS chain   Research agent
STT/LLM  ElevenLabs  NVIDIA NIM or Groq
   |      -> Kokoro       |
   +----------+-----------+
              |
      Supermemory Local (6767)
```

Supermemory and its data stay local. Groq, ElevenLabs, and NVIDIA are optional cloud inference providers configured through environment variables.

## Requirements

- macOS (meeting capture and local voice fallbacks are macOS-oriented)
- Node.js and npm
- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- A running Supermemory Local server
- A Groq API key for the default LLM and speech-to-text path

Optional:

- ElevenLabs API key for primary TTS
- NVIDIA API key for the larger background research model
- Local Kokoro model at `.models/Kokoro-82M-4bit`

## Install

```bash
npm ci --prefix web
uv sync --project tools/qwen-tts-mlx
```

Local runtime data, models, generated audio, and secrets are ignored by Git.

## Configure

Set secrets in your shell or a local ignored environment file. Never commit them.

```bash
export GROQ_API_KEY="..."
export ELEVENLABS_API_KEY="..."       # optional
export NVIDIA_API_KEY="..."           # optional

export SUPERMEMORY_URL="http://127.0.0.1:6767"
export SUPERMEMORY_CONTAINER="hackathon-user"
export MEETING_CONTAINER="jarvis-meeting-demo"
export TTS_PROVIDER="elevenlabs"       # groq, elevenlabs, kokoro, or qwen
```

Useful optional overrides include `GROQ_MODEL`, `GROQ_FALLBACK_MODEL`, `GROQ_STT_MODEL`, `ELEVENLABS_TTS_VOICE_ID`, `NVIDIA_RESEARCH_MODEL`, `KOKORO_VOICE`, and `KOKORO_SPEED`.

## Run

Start Supermemory Local on port `6767`, then run the backend:

```bash
uv run --project tools/qwen-tts-mlx \
  uvicorn realtime_voice_server:app --host 127.0.0.1 --port 8787
```

In another terminal, start the dashboard:

```bash
npm run dev --prefix web -- --host 127.0.0.1
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173).

## Demo flow

1. Confirm that the Supermemory card says **Connected**.
2. Start meeting capture and select a meeting window with system audio.
3. End capture and show the timestamped transcript and generated meeting brief.
4. Ask JARVIS what the meeting requested; it recalls Supermemory before answering.
5. Enter a research question and click **Research current query**.
6. Show the live agent state, then open a completed sourced brief.
7. Use push-to-talk for a final concise voice recall.

Suggested research prompt:

> Research the recommended architecture for a consent-based macOS meeting assistant using ScreenCaptureKit for shared-screen and system-audio capture, with microphone input, privacy, and low latency.

## Validation

Build the frontend:

```bash
npm run build --prefix web
```

Compile the Python entry points:

```bash
python3 -m py_compile realtime_voice_server.py meeting_agent.py scripts/*.py
```

The `scripts/` directory contains focused smoke tests for conversation history, streaming voice, meeting summarization, LLM access, and research jobs. Some tests require the local services and configured provider keys.

## Repository layout

```text
web/                         React dashboard
realtime_voice_server.py     FastAPI, WebSockets, STT/TTS, meeting capture
meeting_agent.py             meeting analysis and background research
scripts/                     smoke tests and local test runners
fixtures/                    deterministic meeting fixtures
tools/qwen-tts-mlx/          reproducible Python/MLX runtime
supermemory-api.json         local Supermemory OpenAPI reference
```

## Privacy and safety

- Meeting capture starts only after explicit screen and microphone permission.
- Recording state remains visible in the interface.
- Suggested terminal commands are displayed but never executed automatically.
- Memory deletion requires explicit confirmation.
- `.supermemory/`, `.env*`, models, caches, generated audio, and logs are excluded from Git.

## One-line pitch

**JARVIS remembers what happened, understands what comes next, and helps finish the work.**
