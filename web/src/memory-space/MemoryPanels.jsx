import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { flightCurve } from "./flightPath.js";

const dummy = new THREE.Object3D();

function buildInstances(count, { tRange, lateralSpread }) {
  const matrices = [];
  for (let i = 0; i < count; i++) {
    const t = THREE.MathUtils.lerp(tRange[0], tRange[1], Math.random());
    const point = flightCurve.getPointAt(t);
    const tangent = flightCurve.getTangentAt(t);
    const normal = new THREE.Vector3(0, 1, 0).cross(tangent).normalize();
    const up = new THREE.Vector3().crossVectors(tangent, normal).normalize();
    const lateral = (Math.random() - 0.5) * lateralSpread;
    const vertical = (Math.random() - 0.5) * lateralSpread * 0.6;

    dummy.position
      .copy(point)
      .addScaledVector(normal, lateral)
      .addScaledVector(up, vertical);
    dummy.lookAt(point);
    dummy.rotateY(Math.random() * Math.PI);
    const scale = 0.6 + Math.random() * 1.8;
    dummy.scale.set(scale, scale * (0.6 + Math.random() * 0.8), 0.08);
    dummy.updateMatrix();
    matrices.push(dummy.matrix.clone());
  }
  return matrices;
}

export default function MemoryPanels() {
  const tealRef = useRef();
  const warmRef = useRef();

  const tealMatrices = useMemo(
    () => buildInstances(220, { tRange: [0.02, 0.92], lateralSpread: 14 }),
    []
  );
  const warmMatrices = useMemo(
    () => buildInstances(18, { tRange: [0.55, 0.95], lateralSpread: 9 }),
    []
  );

  useLayoutEffect(() => {
    tealMatrices.forEach((matrix, i) => tealRef.current.setMatrixAt(i, matrix));
    tealRef.current.instanceMatrix.needsUpdate = true;
    warmMatrices.forEach((matrix, i) => warmRef.current.setMatrixAt(i, matrix));
    warmRef.current.instanceMatrix.needsUpdate = true;
  }, [tealMatrices, warmMatrices]);

  return (
    <group>
      <instancedMesh ref={tealRef} args={[null, null, tealMatrices.length]}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial
          color="#0c2230"
          emissive="#3fe0d0"
          emissiveIntensity={1.1}
          roughness={0.35}
          metalness={0.2}
        />
      </instancedMesh>
      <instancedMesh ref={warmRef} args={[null, null, warmMatrices.length]}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial
          color="#2a1204"
          emissive="#ff9a3d"
          emissiveIntensity={1.6}
          roughness={0.3}
          metalness={0.1}
        />
      </instancedMesh>
    </group>
  );
}
