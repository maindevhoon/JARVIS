import { usePhaseStore } from "../store.js";

export default function IntroOverlay() {
  const phase = usePhaseStore((s) => s.phase);
  const introOffset = usePhaseStore((s) => s.introOffset);

  const hintOpacity = Math.max(0, 1 - introOffset * 14);
  const wrapperOpacity = phase === "intro" ? 1 : 0;

  return (
    <div
      className="intro-overlay"
      style={{ opacity: wrapperOpacity, pointerEvents: "none" }}
    >
      <div className="intro-heading">
        <span className="intro-eyebrow">JARVIS Core</span>
        <h1>System Initializing</h1>
      </div>
      <div className="intro-hint" style={{ opacity: hintOpacity }}>
        Loading memory systems · scroll to accelerate
      </div>
      <div className="intro-progress">
        <div
          className="intro-progress-bar"
          style={{ width: `${Math.min(100, introOffset * 100)}%` }}
        />
      </div>
    </div>
  );
}
