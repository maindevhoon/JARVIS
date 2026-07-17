import * as THREE from "three";

const controlPoints = [
  new THREE.Vector3(0, 0, 10),
  new THREE.Vector3(3, 1.2, -12),
  new THREE.Vector3(-4.5, -1, -38),
  new THREE.Vector3(2.5, 2, -68),
  new THREE.Vector3(-2, 0.2, -102),
  new THREE.Vector3(0.5, 0.8, -140),
  new THREE.Vector3(0, 0, -178),
];

export const flightCurve = new THREE.CatmullRomCurve3(
  controlPoints,
  false,
  "catmullrom",
  0.4
);

export const PORTAL_POINT = controlPoints[controlPoints.length - 1];
