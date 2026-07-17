import { useEffect, useRef, useState } from "react";
import { useJarvisVoice } from "./useJarvisVoice.js";
import { usePhaseStore } from "../store.js";

export default function ChatPanel() {
  const phase = usePhaseStore((s) => s.phase);
  const {
    inputText,
    setInputText,
    answerText,
    statusText,
    metricsText,
    sending,
    ask,
    listening,
    muted,
    micState,
    level,
    startListening,
    toggleMute,
  } = useJarvisVoice();
  const textareaRef = useRef(null);
  const [listenError, setListenError] = useState("");

  useEffect(() => {
    if (phase === "assistant") textareaRef.current?.focus();
  }, [phase]);

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      ask();
    }
  };

  const handleListen = () => {
    setListenError("");
    startListening().catch((error) => setListenError(`Mic error: ${error.message}`));
  };

  return (
    <div
      className={`chat-panel${phase === "assistant" ? " chat-panel--active" : ""}`}
      style={{ pointerEvents: phase === "assistant" ? "auto" : "none" }}
    >
      <main>
        <h1>Jarvis</h1>
        <div className="answer">
          {answerText || "Ready. Ask a question or start listening."}
        </div>
        <textarea
          ref={textareaRef}
          rows={4}
          placeholder="Your transcript appears here…"
          value={inputText}
          onChange={(event) => setInputText(event.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="mic-controls">
          <button
            className={`secondary${listening ? " live" : ""}`}
            onClick={handleListen}
            disabled={listening}
          >
            {listening ? "Listening" : "Start listening"}
          </button>
          <button
            className={`secondary${muted ? " live" : ""}`}
            onClick={toggleMute}
            disabled={!listening}
          >
            {muted ? "Unmute" : "Mute"}
          </button>
          <span className="mic-state">{listenError || micState}</span>
          <span className="level">
            <i style={{ width: `${level * 100}%` }} />
          </span>
        </div>
        <footer>
          <span className="status">{statusText}</span>
          <span className="metrics">{metricsText}</span>
          <button onClick={() => ask()} disabled={sending}>
            Ask
          </button>
        </footer>
      </main>
    </div>
  );
}
