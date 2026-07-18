import { useEffect, useRef, useState } from "react";
import { useJarvisVoice } from "./useJarvisVoice.js";
import ResearchStatus from "./ResearchStatus.jsx";
import MeetingCapture from "./MeetingCapture.jsx";

const Icon = ({ name }) => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    {name === "mic" && <><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/></>}
    {name === "send" && <><path d="m21 3-7.4 18-3.1-7.5L3 10.4 21 3Z"/><path d="m21 3-10.5 10.5"/></>}
    {name === "mute" && <><path d="M11 5 6 9H3v6h3l5 4V5ZM16 9l5 6m0-6-5 6"/></>}
  </svg>
);

export default function ChatPanel() {
  const {
    inputText, setInputText, answerText, statusText, metricsText, sending, ask,
    listening, muted, pushToTalkActive, micState, level, startListening,
    toggleMute, togglePushToTalk,
  } = useJarvisVoice();
  const inputRef = useRef(null);
  const autoScrolledAnswerRef = useRef("");
  const [listenError, setListenError] = useState("");
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning." : hour < 18 ? "Good afternoon." : "Good evening.";

  const listen = () => {
    setListenError("");
    startListening().catch((error) => setListenError(`Microphone unavailable: ${error.message}`));
  };

  useEffect(() => {
    const normalized = answerText.toLowerCase();
    const pointsToBrief = [
      "details are available below", "details available below", "more information is in the brief",
      "more info is in the brief", "see the brief below", "details are in the brief",
    ].some((phrase) => normalized.includes(phrase));
    if (!pointsToBrief || autoScrolledAnswerRef.current === answerText) return;
    autoScrolledAnswerRef.current = answerText;
    const timer = setTimeout(() => {
      document.getElementById("jarvis-briefs")?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "start",
      });
    }, 350);
    return () => clearTimeout(timer);
  }, [answerText]);

  return (
    <div className="workspace-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-dot"/><b>Jarvis</b><span>Personal workspace</span></div>
        <div className="connection"><i className={sending ? "is-busy" : ""}/>{statusText}</div>
      </header>

      <div className="workspace">
        <section className="welcome">
          <div><span className="eyebrow">YOUR DAY, WITH CONTEXT</span><h1>{greeting}</h1><p>Your meetings, memory, and background research—kept in context.</p></div>
          <time>{new Date().toLocaleDateString([], { weekday:"long", month:"long", day:"numeric" })}</time>
        </section>

        <section className={`universal-search${listening && !muted ? " is-listening" : ""}`}>
          <button
            className={`search-mic${pushToTalkActive ? " is-recording" : ""}`}
            onClick={listening ? togglePushToTalk : listen}
            disabled={muted}
            aria-label={!listening ? "Enable microphone" : pushToTalkActive ? "Finish recording" : "Push to talk"}
            aria-pressed={pushToTalkActive}
            title={!listening ? "Enable microphone" : pushToTalkActive ? "Tap to finish" : "Push to talk"}
          ><Icon name="mic"/></button>
          <textarea
            ref={inputRef} rows={1} value={inputText}
            placeholder={listening ? "Listening…" : "Ask Jarvis or search your memory"}
            onChange={(event) => setInputText(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); if (!sending) ask(); } }}
          />
          {listening && <div className="voice-level"><i style={{width:`${Math.max(4, level * 100)}%`}}/></div>}
          <button className={`mute-button${muted ? " is-muted" : ""}`} onClick={toggleMute} disabled={!listening} aria-label={muted ? "Unmute" : "Mute"} aria-pressed={muted}><Icon name="mute"/></button>
          <button className="search-submit" onClick={() => ask()} disabled={sending || !inputText.trim()} aria-label="Ask Jarvis"><Icon name="send"/></button>
        </section>
        <div className="search-meta"><span>{listenError || micState}</span><span>{metricsText || "Enter to ask · Shift + Enter for a new line"}</span></div>

        {answerText && (
          <section className="jarvis-answer">
            <div className="answer-label"><span>J</span><b>Jarvis</b><small>Based on your memory</small></div>
            <div className="answer-text">{answerText}</div>
          </section>
        )}

        <MeetingCapture />
        <ResearchStatus question={inputText} />
      </div>
    </div>
  );
}
