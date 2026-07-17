import { Canvas } from "@react-three/fiber";
import { ScrollControls } from "@react-three/drei";
import * as THREE from "three";
import CameraRig from "./CameraRig.jsx";
import MemoryPanels from "./MemoryPanels.jsx";
import CorePortal from "./CorePortal.jsx";
import Effects from "./Effects.jsx";
import { usePhaseStore } from "../store.js";

export default function Scene() {
  const phase = usePhaseStore((s) => s.phase);

  return (
    <Canvas
      gl={{
        antialias: false,
        toneMapping: THREE.ACESFilmicToneMapping,
        toneMappingExposure: 1.1,
      }}
      camera={{ position: [0, 0, 10], fov: 55, near: 0.1, far: 400 }}
      style={{ position: "fixed", inset: 0 }}
    >
      <color attach="background" args={["#04070a"]} />
      <fog attach="fog" args={["#04080a", 20, 140]} />
      <ambientLight intensity={0.25} />
      <pointLight position={[0, 5, 5]} intensity={0.6} color="#8ff5ff" />
      <ScrollControls
        pages={6}
        damping={0.45}
        maxSpeed={0.6}
        enabled={phase === "intro"}
      >
        <CameraRig />
        <MemoryPanels />
        <CorePortal />
      </ScrollControls>
      <Effects />
    </Canvas>
  );
}
