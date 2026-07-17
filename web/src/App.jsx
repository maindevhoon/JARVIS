import Scene from "./memory-space/Scene.jsx";
import IntroOverlay from "./memory-space/IntroOverlay.jsx";
import ChatPanel from "./voice-ui/ChatPanel.jsx";

export default function App() {
  return (
    <>
      <Scene />
      <IntroOverlay />
      <ChatPanel />
    </>
  );
}
