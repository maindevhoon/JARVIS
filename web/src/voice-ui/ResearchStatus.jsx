import { useCallback, useEffect, useState } from "react";

const ACTIVE = new Set(["queued", "running"]);
const labelFor = (job) => job.stage?.replaceAll("_", " ") || job.status;
const lastEvent = (job) => job.events?.at(-1)?.message || labelFor(job);
const briefText = (job) => {
  const report = job.result?.report || job.result?.reports?.[0];
  return report?.executiveSummary || report?.answer || report?.recommendation || report?.findings?.[0]?.point || "Research completed and saved to memory.";
};

const conciseMeetingFallback = (text) => {
  const clean = text.replace(/\s+/g, " ").trim();
  if (!clean) return "Meeting captured; no spoken summary was available.";
  if (clean.length <= 240) return clean;
  return `${clean.slice(0, 240).replace(/\s+\S*$/, "")}…`;
};

const briefDetailCache = new Map();

async function loadStoredBrief(document) {
  const cached = briefDetailCache.get(document.id);
  if (cached?.updatedAt === document.updatedAt) return cached.brief;
  const response = await fetch(`/supermemory/v3/documents/${document.id}`, {cache:"no-store"});
  if (!response.ok) throw new Error(`Supermemory brief HTTP ${response.status}`);
  const detail = await response.json();
  let stored;
  try { stored = JSON.parse(detail.content || "{}"); }
  catch { return null; }
  const kind = document.metadata?.kind;
  const sourceJobId = document.metadata?.jobId || document.id;
  let brief;
  if (kind === "captured-meeting") {
    const summary = stored.summary || {};
    const transcript = stored.transcript || "";
    brief = {
      jobId:`memory-${document.id}`, sourceJobId, type:"meeting",
      title:summary.title || "Meeting brief", createdAt:detail.createdAt || document.createdAt,
      status:"completed", stage:"completed", events:[{message:"Synchronized from Supermemory"}],
      result:{report:{title:summary.title || "Meeting brief",executiveSummary:summary.summary || conciseMeetingFallback(transcript)},extraction:{...summary,summary:summary.summary || conciseMeetingFallback(transcript)}}
    };
  } else if (kind === "research-report") {
    const report = stored.report || stored;
    brief = {
      jobId:`memory-${document.id}`, sourceJobId, type:"research",
      title:report.title || "Research brief", createdAt:detail.createdAt || document.createdAt,
      status:"completed", stage:"completed", events:[{message:"Synchronized from Supermemory"}],
      result:{report}
    };
  } else return null;
  briefDetailCache.set(document.id, {updatedAt:document.updatedAt, brief});
  return brief;
}

async function loadMemoryDirectly() {
  const containers = ["hackathon-user", "jarvis-meeting-demo"];
  const listAll = async (path, key, tag) => {
    const items = [];
    for (let page = 1; ; page += 1) {
      const response = await fetch(`/supermemory${path}`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({containerTags:[tag], limit:100, page})});
      if (!response.ok) throw new Error(`Supermemory HTTP ${response.status}`);
      const data = await response.json(); items.push(...(data[key] || []));
      if (page >= (data.pagination?.totalPages || 1)) return items;
    }
  };
  const batches = await Promise.all([
    ...containers.map((tag) => listAll("/v3/documents/list", "memories", tag)),
    ...containers.map((tag) => listAll("/v4/memories/list", "memoryEntries", tag)),
  ]);
  const documents = new Map(batches.slice(0, 2).flat().filter((item) => item.id).map((item) => [item.id, item]));
  const memories = new Map(batches.slice(2).flat().filter((item) => item.id && !item.isForgotten).map((item) => [item.id, item]));
  const categoryMap = {};
  documents.forEach((item) => { const kind = item.metadata?.kind || "conversation"; categoryMap[kind] = (categoryMap[kind] || 0) + 1; });
  const briefDocuments = [...documents.values()]
    .filter((item) => ["captured-meeting", "research-report"].includes(item.metadata?.kind))
    .sort((a,b) => String(b.createdAt || "").localeCompare(String(a.createdAt || "")))
    .slice(0, 20);
  const briefs = (await Promise.all(briefDocuments.map(loadStoredBrief))).filter(Boolean);
  return {connected:true, structuredMemories:memories.size, uniqueDocuments:documents.size,
    categories:Object.entries(categoryMap).sort((a,b) => b[1]-a[1]).slice(0,4).map(([name,count]) => ({name:name.replaceAll("-"," "),count})),
    briefs};
}

export default function ResearchStatus({ question }) {
  const [jobs, setJobs] = useState([]);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [memory, setMemory] = useState(null);

  const refresh = useCallback(async () => {
    const [jobsResult, memoryResult] = await Promise.allSettled([
      Promise.all([
        fetch("/research/jobs?limit=20", {cache:"no-store"}),
        fetch("/meetings/sessions?limit=20", {cache:"no-store"}),
      ]).then(async ([response, meetingsResponse]) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const research = (await response.json()).jobs || [];
        const sessions = meetingsResponse.ok ? (await meetingsResponse.json()).sessions || [] : [];
        const meetingBriefs = sessions.filter((session) => session.status === "completed" && session.result).map((session) => {
          const raw = session.result.summary || {};
          const attendeeText = (session.segments || []).filter((item) => item.source !== "Dev").map((item) => item.text).join(" ");
          const summary = raw.summary || conciseMeetingFallback(attendeeText);
          return {jobId:`meeting-${session.sessionId}`,type:"meeting",title:raw.title || session.title || "Meeting brief",createdAt:session.createdAt,status:"completed",stage:"completed",events:[{message:"Meeting summarized and stored"}],result:{report:{title:raw.title || session.title || "Meeting brief",executiveSummary:summary},extraction:{...raw,summary}}};
        });
        return {jobs:[...research, ...meetingBriefs].sort((a,b) => String(b.createdAt).localeCompare(String(a.createdAt)))};
      }),
      loadMemoryDirectly(),
    ]);
    if (jobsResult.status === "fulfilled" && memoryResult.status === "fulfilled") {
      const merged = new Map();
      for (const job of jobsResult.value.jobs || []) merged.set(job.sourceJobId || job.jobId.replace(/^meeting-/, ""), job);
      for (const brief of memoryResult.value.briefs || []) merged.set(brief.sourceJobId, brief);
      setJobs([...merged.values()].sort((a,b) => String(b.createdAt || "").localeCompare(String(a.createdAt || ""))));
      setError("");
    } else if (jobsResult.status === "fulfilled") {
      setJobs(jobsResult.value.jobs || []); setError("");
    } else {
      setError(`Couldn’t load activity: ${jobsResult.reason.message}`);
    }
    if (memoryResult.status === "fulfilled") setMemory(memoryResult.value);
    else setMemory({connected:false, error:memoryResult.reason.message});
  }, []);
  useEffect(() => { refresh(); const timer = setInterval(refresh, 1500); return () => clearInterval(timer); }, [refresh]);

  const startResearch = async () => {
    if (!question.trim()) return;
    setStarting(true); setError("");
    try {
      const response = await fetch("/research/jobs", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({question:question.trim()}) });
      const data = await response.json();
      if (!response.ok || data.error) throw new Error(data.error || `HTTP ${response.status}`);
      await refresh();
    } catch (e) { setError(`Couldn’t start research: ${e.message}`); }
    finally { setStarting(false); }
  };

  const active = jobs.filter((job) => ACTIVE.has(job.status));
  const completed = jobs.filter((job) => job.status === "completed");

  return (
    <div className="dashboard">
      <section className="dashboard-section activity-section">
        <div className="section-heading"><div><h2>Supermemory board</h2><p>Jarvis’s synchronized long-term context</p></div><span className={`memory-health${memory?.connected ? " is-online" : ""}${!memory ? " is-syncing" : ""}`}>{!memory ? "Syncing" : memory.connected ? "Connected" : "Unavailable"}</span></div>
        <div className="memory-overview">
          {!memory && <div className="empty-state">Loading memory status…</div>}
          {memory && !memory.connected && <div className="empty-state">Supermemory is unavailable.</div>}
          {memory?.connected && <>
            <div className="memory-stats"><div><b>{memory.structuredMemories}</b><span>Structured memories</span></div><div><b>{memory.uniqueDocuments}</b><span>Documents</span></div></div>
            <div className="memory-categories">{memory.categories.filter((item) => !item.name.includes("test")).map((item) => <span key={item.name}><b>{item.count}</b> {item.name}</span>)}</div>
          </>}
        </div>
      </section>

      <section className="dashboard-section agents-section">
        <div className="section-heading"><div><h2>Research agents</h2><p>{active.length ? `${active.length} working now` : "Ready when you are"}</p></div><span className={`agent-indicator${active.length ? " is-active" : ""}`}/></div>
        <button className="research-action" onClick={startResearch} disabled={starting || !question.trim()}>{starting ? "Starting…" : "Research current query"}</button>
        <div className="agent-list">
          {active.length === 0 && <div className="agent-empty"><span>✓</span><div><b>Nothing running</b><p>Completed work will appear in your briefs.</p></div></div>}
          {active.map((job) => <article className="agent-row" key={job.jobId}><div className="agent-spinner"/><div><b>{job.title}</b><p>{labelFor(job)} · {job.provider}</p></div></article>)}
        </div>
        {error && <div className="inline-error">{error}</div>}
      </section>

      <section className="dashboard-section briefs-section" id="jarvis-briefs">
        <div className="section-heading"><div><h2>Briefs</h2><p>Answers prepared by Jarvis</p></div><span className="brief-count">{completed.length}</span></div>
        <div className="brief-grid">
          {completed.length === 0 && <div className="empty-state">Completed research briefs will collect here.</div>}
          {completed.slice(0, 3).map((job) => (
            <article className="brief-card" key={job.jobId} onClick={() => setSelected(job)}>
              <div className="brief-meta"><span>{job.type === "meeting" ? "Meeting brief" : "Research brief"}</span><time>{new Date(job.createdAt).toLocaleDateString([], {month:"short",day:"numeric"})}</time></div>
              <h3>{job.title}</h3><p>{briefText(job)}</p>
              <div className="brief-footer"><span>{job.type === "meeting" ? "Saved to Supermemory" : `${(job.result?.report || job.result?.reports?.[0])?.sources?.length || 0} sources`}</span><button onClick={(event) => { event.stopPropagation(); setSelected(job); }}>Open brief →</button></div>
            </article>
          ))}
        </div>
      </section>
      {selected && <BriefDialog job={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function BriefDialog({ job, onClose }) {
  const report = job.result?.report || job.result?.reports?.[0];
  const extraction = job.result?.extraction;
  const commands = report?.commandPlan || extraction?.commandPlan || [];
  return (
    <div className="brief-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="brief-modal" role="dialog" aria-modal="true" aria-label={job.title}>
        <header><div><span>{job.type === "meeting" ? "Meeting details" : "Research brief"}</span><h2>{report?.title || job.title}</h2></div><button onClick={onClose} aria-label="Close details">×</button></header>
        <div className="brief-modal-body">
          <p className="brief-summary">{report?.executiveSummary || extraction?.summary || lastEvent(job)}</p>
          {extraction?.actionItems?.length > 0 && <DetailList title="Action items" items={extraction.actionItems.map((item) => item.task)} />}
          {report?.findings?.length > 0 && <DetailList title="Findings" items={report.findings.map((item) => item.point)} />}
          {commands.length > 0 && <div className="command-plan"><h3>Suggested terminal commands <span>Not executed</span></h3>{commands.map((item, index) => <div className="command-row" key={`${item.command}-${index}`}><code>{item.command}</code><p>{item.purpose}{item.requiresApproval ? " · Approval required" : ""}</p><button onClick={() => navigator.clipboard.writeText(item.command)}>Copy</button></div>)}</div>}
          {report?.recommendation && <DetailList title="Recommendation" items={[report.recommendation]} />}
          {report?.sources?.length > 0 && <div className="brief-sources"><h3>Sources</h3>{report.sources.map((source) => <a key={source.sourceId} href={source.url} target="_blank" rel="noreferrer">{source.title}</a>)}</div>}
        </div>
      </section>
    </div>
  );
}

function DetailList({ title, items }) {
  return <div className="modal-detail"><h3>{title}</h3><ul>{items.map((item, index) => <li key={`${title}-${index}`}>{item}</li>)}</ul></div>;
}
