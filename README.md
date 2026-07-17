# Jarvis Memory Space MVP

A React and WebGL prototype of the cinematic Jarvis memory-space interface.

## Run it

From this folder:

```bash
pnpm install
pnpm dev
```

Then open `http://localhost:4173`.

## Demo flow

1. Watch the ambient memory-city idle state.
2. Ask “What happened in my meetings today?” or “What did I promise to deliver?”
3. The interface moves through retrieval, synthesis, streaming answer, and evidence states.
4. Click the microphone for a simulated voice-input interaction.
5. Press Escape to return to idle or Command/Ctrl + K to focus the query box.

The MVP uses deterministic mock answers. The `ask()` function in `src/App.jsx` is the integration boundary for a real LLM and Supermemory Local.
