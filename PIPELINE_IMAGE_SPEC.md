# JARVIS Complete Pipeline — Image Generation Specification

Use this document to regenerate architecture diagrams, hackathon slides, posters, or product visuals for JARVIS without losing technical accuracy.

## One-line description

JARVIS is a local-first personal assistant that captures user-authorized meetings, understands and stores their context in Supermemory, performs follow-up research, and returns concise spoken answers with full briefs available in its workspace.

## Complete system pipeline

```text
USER CONSENT
    |
    v
MEETING CAPTURE
    |- Shared screen/video
    |- System audio: Meeting attendees
    |- Microphone: Dev
    |- Date and time
    |- Timezone and locale
    |- Meeting platform and capture surface
    |
    v
AUDIO SEGMENTATION
    |- 12-second meeting segments
    |- WebM / Opus media
    |- Separate microphone and system-audio tracks
    |
    v
SPEECH TO TEXT
    |- Groq Whisper Large V3
    |- Whisper Large V3 Turbo fallback
    |- Speaker attribution
    |- Relative timestamps
    |
    v
MEETING INTELLIGENCE
    |- Concise meeting summary
    |- Participants
    |- Decisions
    |- Action items, owners, and due dates
    |- Open questions
    |- Key moments
    |- Safe suggested terminal commands
    |
    +--------------------------+
    |                          |
    v                          v
SUPERMEMORY LOCAL         BACKGROUND RESEARCH
    |- Full transcript         |- Detect follow-up question
    |- Meeting context         |- Recall relevant memory
    |- Structured summary      |- Decompose research task
    |- Research reports        |- Search primary sources
    |- Conversation history    |- Generate evidence-backed draft
    |- Durable memory          |- Critic reviews claims/citations
    |                          |- Produce recommendation
    |                          |- Store report in Supermemory
    +-------------+------------+
                  |
                  v
JARVIS ORCHESTRATOR
    |- Fresh Supermemory recall before every answer
    |- Current conversation history
    |- Groq GPT-OSS 120B
    |- GPT-OSS 20B fallback on rate limits
    |- Concise, speakable response generation
    |
    +---------------------------+
    |                           |
    v                           v
JARVIS WORKSPACE           REAL-TIME VOICE
    |- Memory status            |- Stream at first punctuation
    |- Live meeting capture     |- ElevenLabs Flash V2.5 primary
    |- Active research jobs     |- Kokoro local fallback
    |- Meeting briefs           |- macOS voice fallback
    |- Research reports         |- Interruptible playback
    |- Full detail modals       |- Push-to-talk / always listening
    |                           |
    +-------------+-------------+
                  |
                  v
             USER DECISION
                  |
                  +----> continued conversation and new memory
```

## Primary flow

1. **Consent** — The user explicitly starts meeting capture and selects the shared surface.
2. **Capture** — JARVIS records screen context, system audio, and microphone input.
3. **Transcribe** — Groq Whisper converts independent audio tracks into attributed, timestamped text.
4. **Understand** — The meeting analyst extracts the outcome, commitments, questions, and safe next steps.
5. **Remember** — The transcript, metadata, and structured brief are stored in Supermemory Local.
6. **Research** — Follow-up questions can become asynchronous, evidence-backed research jobs.
7. **Recall** — Every JARVIS response begins with a fresh Supermemory lookup while retaining conversation history.
8. **Respond** — The answer streams as text and is synthesized by ElevenLabs, with Kokoro as the local fallback.
9. **Present** — The dashboard shows memory health, active work, meeting briefs, and research reports.

## Important loops

### Memory loop

Every conversation, meeting, and completed report can become new Supermemory context. Future queries recall this context before inference.

### Research loop

A meeting action or direct user query starts background research. The reviewed report returns to Supermemory and then appears in Briefs.

### Conversation loop

The current session retains recent user and assistant messages. Supermemory provides long-term context; conversation history provides short-term continuity.

### Voice fallback loop

ElevenLabs is the primary TTS provider. If it fails or is rate-limited, JARVIS uses local Kokoro. A macOS system voice is available as a final fallback.

## Component details

| Layer | Component | Responsibility |
|---|---|---|
| Interface | React + Vite | Dashboard, capture controls, briefs, research state |
| Visual layer | React Three Fiber | Restrained ambient background |
| Transport | WebSockets | Streaming answer tokens, audio chunks, and transcription |
| API | FastAPI | Voice orchestration, meetings, research, memory overview |
| Speech input | Groq Whisper | Real-time and meeting transcription |
| Main inference | Groq GPT-OSS | JARVIS responses and meeting analysis |
| Research inference | NVIDIA NIM or Groq | Background research and evidence criticism |
| Memory | Supermemory Local | Documents, structured memories, search, conversations |
| Primary speech | ElevenLabs Flash | Low-latency natural voice |
| Local speech | Kokoro | Offline/local fallback voice |

## Exact labels for diagrams

Use these labels verbatim when the image generator must render text:

- `JARVIS — FROM MEETING CONTEXT TO ACTION`
- `Consented capture`
- `Screen · System audio · Microphone`
- `Speech and context`
- `Transcription · Speakers · Time · Platform`
- `Meeting intelligence`
- `Summary · Decisions · Actions · Questions`
- `Supermemory Local`
- `Durable context · Fresh recall`
- `Background research`
- `Evidence · Review · Sources · Recommendation`
- `JARVIS orchestrator`
- `Memory recall · Conversation continuity`
- `JARVIS workspace`
- `Memory status · Agents · Briefs`
- `Real-time response`
- `Groq LLM → ElevenLabs`
- `Kokoro fallback`
- `Capture → Understand → Remember → Research → Respond`

## Recommended visual structure

- Canvas: landscape 16:9.
- Primary flow: left to right.
- Supermemory: visually emphasized central hub.
- Background research: one lower branch returning to Supermemory.
- Conversation continuity: a thin feedback arrow from response to Supermemory.
- Dashboard and voice: separate outputs after orchestration.
- Use six or seven large blocks maximum; place detailed technologies in subtitles.
- Keep at least 8% outer margin and generous spacing between blocks.

## Visual direction

- Style: premium editorial information design.
- Mood: calm, capable, trustworthy, technical.
- Background: flat near-black.
- Panels: charcoal with thin gray borders.
- Primary text: off-white.
- Memory and active-state accent: restrained mint.
- Background-research accent: muted amber.
- Connectors: one-pixel white or mint lines with simple arrowheads.
- Icons: minimal outline icons for screen, microphone, transcript, database, research, brief, and waveform.
- Typography: neutral grotesk/sans-serif with strong hierarchy.
- Finish: crisp and vector-like, not glossy.

## Avoid

- Robot faces, humanoid assistants, or Iron Man imagery
- Glowing brains, neural-network webs, and circuit-board backgrounds
- Cyberpunk blue, heavy neon, holograms, or lens flares
- Glassmorphism, glossy 3D blocks, or perspective diagrams
- Fake terminal code or decorative unreadable microtext
- Excess arrows, crossing lines, and duplicated concepts
- Unsupported claims that every component is fully local
- Provider logos unless explicitly needed
- Any secret, API key, personal identifier, or private memory content

## Reusable image-generation prompt

```text
Use case: infographic-diagram
Asset type: polished 16:9 hackathon presentation architecture graphic

Create an end-to-end pipeline diagram for JARVIS, a local-first meeting-aware personal assistant powered by Supermemory. The graphic must look intentionally designed by a senior product designer, not like generic AI-generated art.

Use a flat near-black editorial canvas, charcoal panels, off-white typography, restrained mint accents for memory and active states, and muted amber only for background research. Use a strict grid, generous negative space, thin connectors, simple outline icons, and no perspective.

Show this primary left-to-right flow:
1. Consented capture — Screen · System audio · Microphone
2. Speech and context — Groq Whisper · Speaker attribution · Time and platform
3. Meeting intelligence — Summary · Decisions · Actions · Open questions
4. Supermemory Local — Durable context · Fresh recall before every response
5. JARVIS orchestrator — Memory recall · Conversation continuity
6. JARVIS workspace — Memory status · Active agents · Meeting and research briefs
7. Real-time response — Groq LLM → ElevenLabs · Kokoro fallback

Add one lower branch from Meeting intelligence to Background research, labeled NVIDIA NIM / Groq · Evidence review · Sources, returning into Supermemory Local. Add a subtle feedback line from Real-time response to Supermemory labeled conversation continuity.

Title: “JARVIS — FROM MEETING CONTEXT TO ACTION”
Subtitle: “Capture → Understand → Remember → Research → Respond”

Keep every label legible and correctly spelled. No logos, people, robots, brains, circuitry, cyberpunk, holograms, neon glow, lens flares, glossy 3D, fake UI chrome, random symbols, watermark, or tiny filler text.
```

## Alternate image variants

### Executive slide

Reduce the pipeline to five stages: Capture, Understand, Remember, Research, Respond. Keep Supermemory central and place provider names in a small technical footer.

### Technical architecture

Show three horizontal layers: Interface, Orchestration, and Intelligence/Storage. Include ports `5173`, `8787`, and `6767`, plus WebSocket connections and cloud/local boundaries.

### Privacy architecture

Draw a clear local-device boundary around the dashboard, FastAPI, Supermemory, Kokoro, and captured data. Place Groq, ElevenLabs, and NVIDIA outside that boundary as optional cloud providers. Highlight explicit consent and provider fallbacks.

### Demo-flow graphic

Use a numbered sequence: Start meeting, Capture context, Generate brief, Save memory, Launch research, Ask JARVIS, Open evidence.
