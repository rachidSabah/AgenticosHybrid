"use client";

import React, { useMemo, useRef, useState, useEffect } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { Trail, Sparkles } from "@react-three/drei";

export interface TaskPacketProps {
  from: [number, number, number];
  to: [number, number, number];
  progress: number;
  color?: string;
  size?: number;
  trailLength?: number;
}

export const TaskPacket: React.FC<TaskPacketProps> = ({
  from,
  to,
  progress,
  color = "#4f6cff",
  size = 0.2,
  trailLength = 2,
}) => {
  const meshRef = useRef<THREE.Mesh>(null);
  const materialRef = useRef<THREE.MeshStandardMaterial>(null);
  const lightRef = useRef<THREE.PointLight>(null);
  const [bursting, setBursting] = useState(false);

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

  useEffect(() => {
    if (progress >= 0.95 && !bursting) {
      setBursting(true);
    } else if (progress < 0.95 && bursting) {
      setBursting(false);
    }
  }, [progress, bursting]);

  useFrame((state) => {
    if (!meshRef.current || !materialRef.current || !lightRef.current) return;
    
    const point = curve.getPoint(Math.max(0, Math.min(1, progress)));
    meshRef.current.position.copy(point);
    lightRef.current.position.copy(point);
    
    const isNearEnd = progress > 0.8;
    const currentScale = isNearEnd ? 1 + (progress - 0.8) * 5 : 1;
    meshRef.current.scale.setScalar(currentScale);
    
    const currentColor = new THREE.Color(color);
    if (isNearEnd) {
      currentColor.lerp(new THREE.Color("#22c55e"), (progress - 0.8) * 5);
    }
    
    materialRef.current.color = currentColor;
    materialRef.current.emissive = currentColor;
    lightRef.current.color = currentColor;
    lightRef.current.intensity = isNearEnd ? 2 : 1;
    
    if (progress >= 1) {
      meshRef.current.visible = false;
      lightRef.current.visible = false;
    } else {
      meshRef.current.visible = true;
      lightRef.current.visible = true;
    }
  });

  return (
    <group>
      <Trail
        width={size * 2}
        length={trailLength}
        color={color}
        attenuation={(t) => t * t}
      >
        <mesh ref={meshRef}>
          <sphereGeometry args={[size, 16, 16]} />
          <meshStandardMaterial
            ref={materialRef}
            color={color}
            emissive={color}
            emissiveIntensity={2}
            toneMapped={false}
          />
        </mesh>
      </Trail>
      
      <pointLight
        ref={lightRef}
        distance={3}
        intensity={1}
        color={color}
      />
      
      {bursting && (
        <group position={curve.getPoint(1)}>
          <Sparkles
            count={20}
            scale={2}
            size={4}
            speed={0.4}
            opacity={1}
            color="#22c55e"
          />
        </group>
      )}
    </group>
  );
};
