import { useEffect, useRef, useState } from "react";

const SEGMENT_MS = 12000;

function toBase64(blob) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result.split(",")[1]);
    reader.readAsDataURL(blob);
  });
}

function elapsedLabel(startedAt) {
  const seconds = Math.floor((Date.now() - startedAt) / 1000);
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function detectMeetingPlatform(label = "") {
  const value = label.toLowerCase();
  if (value.includes("zoom")) return "Zoom";
  if (value.includes("meet.google") || value.includes("google meet")) return "Google Meet";
  if (value.includes("teams") || value.includes("microsoft teams")) return "Microsoft Teams";
  if (value.includes("webex")) return "Cisco Webex";
  if (value.includes("slack")) return "Slack Huddle";
  if (value.includes("discord")) return "Discord";
  if (value.includes("facetime")) return "FaceTime";
  return "Unknown meeting platform";
}

function DetailGroup({ title, items, renderItem }) {
  if (!items?.length) return null;
  return (
    <div className="brief-detail-group">
      <h4>{title} <span>{items.length}</span></h4>
      <ol>{items.map((item, index) => <li key={`${title}-${index}`}>{renderItem(item)}</li>)}</ol>
    </div>
  );
}

function CommandGroup({ commands }) {
  if (!commands?.length) return null;
  return (
    <div className="meeting-command-plan">
      <h4>Suggested terminal commands <span>Not executed</span></h4>
      {commands.map((item, index) => (
        <div className="command-row" key={`${item.command}-${index}`}>
          <code>{item.command}</code>
          <p>{item.purpose}{item.requiresApproval ? " · Approval required" : ""}</p>
          <button onClick={() => navigator.clipboard.writeText(item.command)}>Copy</button>
        </div>
      ))}
    </div>
  );
}

export default function MeetingCapture() {
  const [session, setSession] = useState(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState("00:00");
  const [systemAudio, setSystemAudio] = useState(false);
  const screenRef = useRef(null);
  const micRef = useRef(null);
  const recorderRefs = useRef(new Set());
  const stoppingRef = useRef(false);
  const startedRef = useRef(0);
  const sessionRef = useRef(null);

  useEffect(() => {
    if (status !== "recording") return;
    const timer = setInterval(() => setElapsed(elapsedLabel(startedRef.current)), 1000);
    return () => clearInterval(timer);
  }, [status]);

  const uploadSegment = async (blob, mimeType, timestamp, source) => {
    if (blob.size < 1000 || !sessionRef.current) return;
    const response = await fetch(`/meetings/sessions/${sessionRef.current.sessionId}/segments`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ audio: await toBase64(blob), mimeType, timestamp, source }),
    });
    const data = await response.json();
    if (data.error) throw new Error(data.error);
    setSession((current) => current ? {...current, segments:[...(current.segments || []), {id:crypto.randomUUID(), timestamp, text:data.text, source}]} : current);
  };

  const recordNextSegment = (stream, source) => {
    if (stoppingRef.current) return;
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
    const recorder = new MediaRecorder(stream, { mimeType });
    let resolveUpload;
    recorder.uploadDone = new Promise((resolve) => { resolveUpload = resolve; });
    const chunks = [];
    const timestamp = elapsedLabel(startedRef.current);
    recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
    recorder.onstop = async () => {
      try { await uploadSegment(new Blob(chunks, {type:mimeType}), mimeType, timestamp, source); }
      catch (e) { setError(`Transcription error: ${e.message}`); }
      recorderRefs.current.delete(recorder);
      resolveUpload();
      if (!stoppingRef.current) recordNextSegment(stream, source);
    };
    recorder.start(); recorderRefs.current.add(recorder);
    setTimeout(() => { if (recorder.state === "recording") recorder.stop(); }, SEGMENT_MS);
  };

  const start = async () => {
    setError(""); setStatus("requesting"); stoppingRef.current = false;
    try {
      const screen = await navigator.mediaDevices.getDisplayMedia({ video:true, audio:true });
      const mic = await navigator.mediaDevices.getUserMedia({ audio:{echoCancellation:true, noiseSuppression:true}, video:false });
      screenRef.current = screen; micRef.current = mic;
      const hasSystemAudio = screen.getAudioTracks().length > 0;
      const videoTrack = screen.getVideoTracks()[0];
      const displaySettings = videoTrack?.getSettings?.() || {};
      const sourceLabel = videoTrack?.label || "Shared screen";
      setSystemAudio(hasSystemAudio);
      const response = await fetch("/meetings/sessions", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({
        title:"Live meeting", screen:true, systemAudio:hasSystemAudio, microphone:true,
        startedAt:new Date().toISOString(), timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,
        locale:navigator.language, platform:detectMeetingPlatform(sourceLabel),
        captureSurface:displaySettings.displaySurface || "unknown", sourceLabel,
      }) });
      const created = await response.json(); sessionRef.current = created; setSession(created);
      startedRef.current = Date.now(); setElapsed("00:00"); setStatus("recording");
      videoTrack.onended = () => { if (!stoppingRef.current) stop(); };
      recordNextSegment(new MediaStream(mic.getAudioTracks()), "Dev");
      if (hasSystemAudio) {
        recordNextSegment(new MediaStream(screen.getAudioTracks()), "Meeting attendees");
      }
    } catch (e) {
      screenRef.current?.getTracks().forEach((track) => track.stop()); micRef.current?.getTracks().forEach((track) => track.stop());
      setError(e.name === "NotAllowedError" ? "Screen or microphone permission was not granted." : e.message); setStatus("idle");
    }
  };

  const stop = async () => {
    if (!sessionRef.current || stoppingRef.current) return;
    stoppingRef.current = true; setStatus("summarizing");
    const recorders = [...recorderRefs.current];
    recorders.forEach((recorder) => { if (recorder.state === "recording") recorder.stop(); });
    await Promise.all(recorders.map((recorder) => recorder.uploadDone));
    screenRef.current?.getTracks().forEach((track) => track.stop()); micRef.current?.getTracks().forEach((track) => track.stop());
    try {
      const response = await fetch(`/meetings/sessions/${sessionRef.current.sessionId}/finish`, {method:"POST"});
      const finished = await response.json();
      if (finished.error) throw new Error(finished.error);
      setSession(finished); setStatus(finished.status);
    } catch (e) { setError(e.message); setStatus("failed"); }
  };

  const rawSummary = session?.result?.summary;
  const attendeeText = (session?.segments || []).filter((item) => item.source !== "Dev").map((item) => item.text).join(" ");
  const summary = session?.result && {
    title: rawSummary?.title || session.title || "Meeting brief",
    summary: rawSummary?.summary || `${attendeeText.slice(0, 420).trim()}${attendeeText.length > 420 ? "…" : ""}` || "The meeting was captured, but no spoken summary was available.",
    decisions: Array.isArray(rawSummary?.decisions) ? rawSummary.decisions : [],
    actionItems: Array.isArray(rawSummary?.actionItems) ? rawSummary.actionItems : [],
    openQuestions: Array.isArray(rawSummary?.openQuestions) ? rawSummary.openQuestions : [],
    commandPlan: Array.isArray(rawSummary?.commandPlan) ? rawSummary.commandPlan : [],
  };
  return (
    <section className="meeting-card">
      <div className="section-heading"><div><h2>Meeting capture</h2><p>Screen, attendees and live notes</p></div><span className={`meeting-state is-${status}`}>{status === "recording" ? elapsed : status}</span></div>
      {status === "idle" || status === "failed" ? (
        <div className="meeting-start"><div><b>Start a meeting session</b><p>You’ll choose the meeting window and approve microphone access. Recording indicators remain visible.</p></div><button onClick={start}>Start capture</button></div>
      ) : (
        <>
          <div className="capture-signals"><span className="is-on">Screen</span><span className={systemAudio ? "is-on" : "is-off"}>System audio</span><span className="is-on">Microphone</span>{status === "recording" && <button onClick={stop}>End & summarize</button>}</div>
          <div className="live-transcript">
            {(session?.segments || []).length === 0 && <p className="transcript-empty">Listening for speech…</p>}
            {(session?.segments || []).slice(-3).map((segment) => <p key={segment.id}><time>{segment.timestamp}</time><span><b>{segment.source}:</b> {segment.text}</span></p>)}
          </div>
        </>
      )}
      {summary && (
        <div className="meeting-summary">
          <span>MEETING BRIEF · SAVED TO SUPERMEMORY</span>
          <h3>{summary.title}</h3><p>{summary.summary}</p>
          <div className="brief-counts"><b>{summary.decisions?.length || 0}</b> decisions <b>{summary.actionItems?.length || 0}</b> actions <b>{summary.openQuestions?.length || 0}</b> open questions</div>
          <div className="brief-details">
            <DetailGroup title="Decisions" items={summary.decisions} renderItem={(item) => item} />
            <DetailGroup title="Action items" items={summary.actionItems} renderItem={(item) => <><strong>{item.task}</strong><small>Owner: {item.owner || "Unassigned"}{item.dueDate ? ` · Due: ${item.dueDate}` : ""}</small></>} />
            <DetailGroup title="Open questions" items={summary.openQuestions} renderItem={(item) => item} />
          </div>
          <CommandGroup commands={summary.commandPlan} />
        </div>
      )}
      {error && <div className="inline-error">{error}</div>}
    </section>
  );
}
