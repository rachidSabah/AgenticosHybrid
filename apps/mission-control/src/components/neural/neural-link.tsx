"use client";

import React, { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Line } from "@react-three/drei";
import * as THREE from "three";

export interface NeuralLinkProps {
  from: [number, number, number];
  to: [number, number, number];
  active?: boolean;
  intensity?: number;
  color?: string;
  bidirectional?: boolean;
  photonCount?: number;
  pulseSpeed?: number;
}

const NeuralLinkComponent: React.FC<NeuralLinkProps> = ({
  from,
  to,
  active = false,
  intensity = 0.5,
  color = "#00f0ff",
  bidirectional = false,
  photonCount = 8,
  pulseSpeed = 1,
}) => {
  const pointsRef = useRef<THREE.Points>(null);
  const materialRef = useRef<THREE.PointsMaterial>(null);
  const lineMaterialRef = useRef<any>(null);
  
  const curve = useMemo(() => {
    const vFrom = new THREE.Vector3(...from);
    const vTo = new THREE.Vector3(...to);
    
    const midX = (vFrom.x + vTo.x) / 2;
    const midY = (vFrom.y + vTo.y) / 2;
    const midZ = (vFrom.z + vTo.z) / 2;
    
    const distance = vFrom.distanceTo(vTo);
    const arcHeight = Math.max(distance * 0.2, 1);
    
    const vMid = new THREE.Vector3(midX, midY + arcHeight, midZ);
    
    return new THREE.QuadraticBezierCurve3(vFrom, vMid, vTo);
  }, [from, to]);

  const curvePoints = useMemo(() => curve.getPoints(50), [curve]);
  
  const photonPositions = useMemo(() => {
    const positions = new Float32Array(photonCount * 3);
    return positions;
  }, [photonCount]);

  const photonProgress = useRef(Array.from({ length: photonCount }, () => Math.random()));
  const photonDirections = useRef(Array.from({ length: photonCount }, () => bidirectional ? (Math.random() > 0.5 ? 1 : -1) : 1));

  useFrame((state, delta) => {
    if (!pointsRef.current || !materialRef.current || !lineMaterialRef.current) return;
    
    const positions = pointsRef.current.geometry.attributes.position.array as Float32Array;
    
    const time = state.clock.elapsedTime;
    const isHeartbeat = !active && Math.sin(time * 2) > 0.8;
    const isActive = active || isHeartbeat;
    
    for (let i = 0; i < photonCount; i++) {
      let progress = photonProgress.current[i];
      const dir = photonDirections.current[i];
      
      const speed = isActive ? pulseSpeed * 0.5 * (0.5 + intensity * 0.5) : pulseSpeed * 0.1;
      progress += dir * delta * speed;
      
      if (progress > 1) progress = 0;
      if (progress < 0) progress = 1;
      
      photonProgress.current[i] = progress;
      
      const point = curve.getPoint(progress);
      positions[i * 3] = point.x;
      positions[i * 3 + 1] = point.y;
      positions[i * 3 + 2] = point.z;
    }
    
    pointsRef.current.geometry.attributes.position.needsUpdate = true;
    
    const targetOpacity = isActive ? 0.8 : 0.2;
    lineMaterialRef.current.opacity = THREE.MathUtils.lerp(lineMaterialRef.current.opacity, targetOpacity, 0.1);
    materialRef.current.opacity = THREE.MathUtils.lerp(materialRef.current.opacity, isActive ? 1 : 0.3, 0.1);
  });

  const lineWidth = 1 + intensity * 3;

  return (
    <group>
      <Line
        points={curvePoints}
        color={color}
        lineWidth={lineWidth}
        transparent
        opacity={0.2}
      >
        <lineBasicMaterial ref={lineMaterialRef} color={color} transparent opacity={0.2} />
      </Line>
      
      <points ref={pointsRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[photonPositions, 3]}
          />
        </bufferGeometry>
        <pointsMaterial
          ref={materialRef}
          size={0.15 + intensity * 0.1}
          color={color}
          transparent
          opacity={0.8}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </points>
    </group>
  );
};

export const NeuralLink = React.memo(NeuralLinkComponent);
