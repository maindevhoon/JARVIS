import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { useScroll } from "@react-three/drei";
import * as THREE from "three";
import { usePhaseStore } from "../store.js";
import { PORTAL_POINT } from "./flightPath.js";

export default function CorePortal() {
  const ringRef = useRef();
  const glowRef = useRef();
  const coreRef = useRef();
  const scroll = useScroll();
  const phase = usePhaseStore((s) => s.phase);

  useFrame((state, delta) => {
    const offset = phase === "intro" ? scroll.offset : 1;
    const reveal = THREE.MathUtils.smoothstep(offset, 0.6, 0.98);
    const idleDamp = phase === "intro" ? 1 : 0.55;
    const scale = (0.2 + reveal * 1.3) * idleDamp;

    if (ringRef.current) {
      ringRef.current.scale.setScalar(scale);
      ringRef.current.rotation.z += delta * 0.15;
    }
    if (glowRef.current) {
      glowRef.current.scale.setScalar(scale * 1.4);
      glowRef.current.material.opacity = (0.25 + reveal * 0.5) * idleDamp;
    }
    if (coreRef.current) {
      coreRef.current.rotation.y += delta * 0.2;
      coreRef.current.rotation.x += delta * 0.08;
    }
  });

  return (
    <group position={[PORTAL_POINT.x, PORTAL_POINT.y, PORTAL_POINT.z - 6]}>
      <mesh ref={coreRef} position={[6, 3, -6]}>
        <icosahedronGeometry args={[2.2, 1]} />
        <meshStandardMaterial
          emissive="#ff9a3d"
          color="#3a1a04"
          emissiveIntensity={2.2}
          roughness={0.25}
        />
      </mesh>
      <mesh ref={glowRef}>
        <circleGeometry args={[5, 48]} />
        <meshBasicMaterial
          color="#8ff5ff"
          transparent
          opacity={0.3}
          side={THREE.DoubleSide}
        />
      </mesh>
      <mesh ref={ringRef}>
        <ringGeometry args={[3.4, 4, 64]} />
        <meshBasicMaterial
          color="#eafcff"
          transparent
          opacity={0.9}
          side={THREE.DoubleSide}
        />
      </mesh>
    </group>
  );
}
