import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { useScroll } from "@react-three/drei";
import * as THREE from "three";
import { usePhaseStore } from "../store.js";
import { flightCurve, PORTAL_POINT } from "./flightPath.js";

const tmpPos = new THREE.Vector3();
const tmpLookAhead = new THREE.Vector3();
const tmpTangent = new THREE.Vector3();
const tmpUp = new THREE.Vector3();
const tmpMatrix = new THREE.Matrix4();
const tmpQuat = new THREE.Quaternion();
const IDLE_TARGET = new THREE.Vector3(
  PORTAL_POINT.x,
  PORTAL_POINT.y,
  PORTAL_POINT.z - 20
);
const AUTO_FLIGHT_DELAY = 0.45;
const AUTO_FLIGHT_DURATION = 4.8;

function easeInOutCubic(value) {
  return value < 0.5
    ? 4 * value * value * value
    : 1 - Math.pow(-2 * value + 2, 3) / 2;
}

export default function CameraRig() {
  const scroll = useScroll();
  const phase = usePhaseStore((s) => s.phase);
  const enterAssistant = usePhaseStore((s) => s.enterAssistant);
  const setIntroOffset = usePhaseStore((s) => s.setIntroOffset);
  const enteredRef = useRef(false);
  const lastOffsetRef = useRef(0);
  const idleClockRef = useRef(0);
  const introClockRef = useRef(0);

  useFrame((state, delta) => {
    const { camera } = state;

    if (phase === "intro") {
      introClockRef.current += delta;
      const elapsed = Math.max(0, introClockRef.current - AUTO_FLIGHT_DELAY);
      const autoProgress = Math.min(1, elapsed / AUTO_FLIGHT_DURATION);
      const offset = Math.max(scroll.offset, easeInOutCubic(autoProgress));
      const deltaOffset = offset - lastOffsetRef.current;
      lastOffsetRef.current = offset;
      setIntroOffset(offset);

      const t = Math.min(offset, 0.999);
      flightCurve.getPointAt(t, tmpPos);
      flightCurve.getTangentAt(t, tmpTangent);

      camera.position.lerp(tmpPos, 1 - Math.pow(0.001, delta));

      tmpLookAhead.copy(tmpPos).addScaledVector(tmpTangent, 6);
      const wobble = Math.sin(offset * Math.PI * 5) * 0.18;
      tmpUp.set(wobble, 1, 0).normalize();
      tmpMatrix.lookAt(camera.position, tmpLookAhead, tmpUp);
      tmpQuat.setFromRotationMatrix(tmpMatrix);
      camera.quaternion.slerp(tmpQuat, 1 - Math.pow(0.0005, delta));

      const speed = Math.abs(deltaOffset) / Math.max(delta, 1e-4);
      camera.fov = THREE.MathUtils.damp(
        camera.fov,
        55 + Math.min(speed * 30, 18),
        4,
        delta
      );
      camera.updateProjectionMatrix();

      if (offset > 0.985 && !enteredRef.current) {
        enteredRef.current = true;
        enterAssistant();
      }
    } else {
      idleClockRef.current += delta;
      const t = idleClockRef.current;
      tmpPos.set(
        PORTAL_POINT.x + Math.sin(t * 0.15) * 1.5,
        PORTAL_POINT.y + Math.cos(t * 0.1) * 0.6,
        PORTAL_POINT.z + 26 + Math.sin(t * 0.08) * 2
      );
      camera.position.lerp(tmpPos, 1 - Math.pow(0.001, delta));
      camera.lookAt(IDLE_TARGET);
      camera.fov = THREE.MathUtils.damp(camera.fov, 50, 4, delta);
      camera.updateProjectionMatrix();
    }
  });

  return null;
}
