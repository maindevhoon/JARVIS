# JARVIS Hackathon Demo Script

Target length: 3–4 minutes

## Before presenting

- Open `http://127.0.0.1:5173/` and confirm Supermemory says **Connected**.
- Keep the microphone muted until the voice section.
- Have a short meeting clip or a second speaker ready.
- Use the prepared research question below so the result is concrete.

## 1. The problem — 20 seconds

**Say:**

“After a meeting, the important context is usually scattered across transcripts, notes, and forgotten action items. JARVIS is a personal AI assistant that listens—with explicit permission—turns meetings into durable memory, and can continue the work after the call ends.”

## 2. Show the workspace — 25 seconds

Point to the Supermemory card and Briefs.

**Say:**

“This is not a chat interface. It is a live workspace. Supermemory gives JARVIS long-term context, meeting briefs collect what matters, and research agents show work happening in the background.”

## 3. Capture a meeting — 60 seconds

Click **Start capture**, choose the meeting window or tab, and share system audio.

Have the other attendee say:

“Dev, before our next meeting, please investigate whether a privacy-first macOS meeting assistant can capture a shared screen, system audio, and microphone with low latency. Compare ScreenCaptureKit with third-party audio routing, and bring back a recommendation with sources.”

Respond:

“Understood. Please make the recommendation concise and include the main privacy trade-offs.”

Click **End & summarize**.

While it processes, **say:**

“JARVIS separates my microphone from meeting attendees, timestamps the transcript, records platform and timezone context, extracts decisions and actions, and saves the result into Supermemory automatically.”

## 4. Show the meeting brief — 35 seconds

Point to the generated summary, decisions, action items, and open questions.

**Say:**

“The transcript is useful, but the brief is the real interface. I immediately get the outcome, assigned work, unanswered questions, and safe suggested commands. Nothing is executed without permission.”

If the assistant says details are below, let the automatic scroll move to Briefs and open the newest brief.

## 5. Start background research — 35 seconds

Enter or speak:

“Research the recommended architecture for a consent-based macOS meeting assistant using ScreenCaptureKit for shared-screen and system-audio capture, with microphone input, privacy, and low latency.”

Click **Research current query**.

**Say:**

“The request becomes a visible background job. JARVIS researches, reviews evidence, prepares a sourced recommendation, and stores the completed report back into Supermemory.”

Open the completed ScreenCaptureKit research brief if the new task is still running.

## 6. Demonstrate personal recall — 35 seconds

Enable the microphone. For reliability during the demo, use push-to-talk: tap the microphone, speak, then tap it again.

**Ask:**

“Jarvis, what did the meeting ask me to investigate?”

Then ask:

“Jarvis, give me the recommendation in one sentence.”

**Say:**

“Every answer starts with a fresh Supermemory recall while preserving the current conversation. That gives JARVIS both long-term memory and natural conversational continuity.”

## 7. Close — 20 seconds

**Say:**

“JARVIS turns meetings into an active workflow: it captures context, remembers commitments, performs follow-up research, and brings the answer back when I need it. The goal is not another AI chat—it is a personal assistant that understands what happened and helps finish what comes next.”

## Backup lines

If meeting summarization is slow:

“The capture is already timestamped and stored. While the summarizer completes, I’ll show a previously generated meeting brief.”

If research is still running:

“Research is intentionally asynchronous. Its live status remains visible, and this completed brief shows the same reviewed output format.”

If voice transcription misses a phrase:

“I’ll use push-to-talk, which isolates this command from room noise.”

If a cloud provider rate-limits:

“The pipeline has provider fallbacks, while the meeting record and Supermemory context remain local and intact.”
