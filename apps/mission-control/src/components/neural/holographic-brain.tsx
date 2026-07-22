"use client";

import React, { useRef, useMemo, useState, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';
import { Sphere } from '@react-three/drei';
import * as THREE from 'three';

export interface HolographicBrainProps {
  position?: [number, number, number];
  scale?: number;
  color?: string;
  pulseSpeed?: number;
  pulseIntensity?: number;
  activity?: 'idle' | 'thinking' | 'reasoning' | 'planning' | 'coding' | 'busy' | 'searching' | 'offline' | 'disconnected';
  isCentral?: boolean;
  opacity?: number;
  onClick?: () => void;
}

const getActivityColor = (activity: HolographicBrainProps['activity'], baseColor: string) => {
  switch (activity) {
    case 'busy': return '#f97316'; // orange
    case 'reasoning': return '#a855f7'; // violet
    case 'planning': return '#4f6cff'; // electric blue
    case 'coding': return '#22c55e'; // green
    case 'searching': return '#00f0ff'; // cyan
    case 'thinking': return '#eab308'; // yellow
    case 'offline': return '#374151'; // gray
    case 'disconnected': return '#1f2937'; // dark gray
    case 'idle':
    default:
      return baseColor || '#00f0ff'; // cyan
  }
};

const createHemisphereGeometry = (isLeft: boolean) => {
  const geo = new THREE.SphereGeometry(1, 32, 32);
  const posAttribute = geo.attributes.position;
  const v = new THREE.Vector3();
  for (let i = 0; i < posAttribute.count; i++) {
    v.fromBufferAttribute(posAttribute, i);
    
    // Scale to make it oblong (brain shape)
    v.y *= 0.8;
    v.z *= 1.2;
    
    // Flatten the medial face (where the hemispheres meet)
    if (isLeft && v.x > 0) v.x *= 0.2;
    if (!isLeft && v.x < 0) v.x *= 0.2;
    
    // Procedural gyri/sulci displacement using sine waves
    const noise = Math.sin(v.x * 10) * Math.cos(v.y * 10) * Math.sin(v.z * 10);
    const displacement = 1 + noise * 0.05;
    
    v.multiplyScalar(displacement);
    posAttribute.setXYZ(i, v.x, v.y, v.z);
  }
  geo.computeVertexNormals();
  return geo;
};

// Subcomponents

const OrbitalRings = React.memo(({ count, targetColor, opacity, speedMultiplier }: { count: number, targetColor: THREE.Color, opacity: number, speedMultiplier: number }) => {
  const ringsRef = useRef<THREE.Group>(null);
  const materialRef = useRef<THREE.MeshBasicMaterial>(null);
  
  useFrame((state, delta) => {
    if (ringsRef.current) {
      ringsRef.current.children.forEach((ring, i) => {
        ring.rotation.x += delta * 0.1 * speedMultiplier * (i % 2 === 0 ? 1 : -1);
        ring.rotation.y += delta * 0.15 * speedMultiplier * (i % 3 === 0 ? 1 : -1);
      });
    }
    if (materialRef.current) {
      materialRef.current.color.lerp(targetColor, delta * 3);
    }
  });

  return (
    <group ref={ringsRef} position={[0, 0.4, 0]}>
      {Array.from({ length: count }).map((_, i) => (
        <mesh key={i} rotation={[Math.random() * Math.PI, Math.random() * Math.PI, 0]}>
          <torusGeometry args={[1.5 + i * 0.2, 0.01, 4, 64]} />
          <meshBasicMaterial 
            ref={i === 0 ? materialRef : undefined}
            color={targetColor} 
            transparent 
            opacity={opacity} 
            blending={THREE.AdditiveBlending} 
            depthWrite={false} 
          />
        </mesh>
      ))}
    </group>
  );
});
OrbitalRings.displayName = 'OrbitalRings';

const BrainParticles = React.memo(({ count, targetColor, activity, opacity }: { count: number, targetColor: THREE.Color, activity: string, opacity: number }) => {
  const pointsRef = useRef<THREE.Points>(null);
  const materialRef = useRef<THREE.PointsMaterial>(null);
  
  const [positions, phases] = useMemo(() => {
    const pos = new Float32Array(count * 3);
    const phs = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(Math.random() * 2 - 1);
      const r = 1.0 + Math.random() * 0.5;
      
      pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      pos[i * 3 + 2] = r * Math.cos(phi);
      
      phs[i] = Math.random() * Math.PI * 2;
    }
    return [pos, phs];
  }, [count]);

  useFrame((state, delta) => {
    if (materialRef.current) {
      materialRef.current.color.lerp(targetColor, delta * 3);
    }

    if (!pointsRef.current || activity === 'offline' || activity === 'disconnected') return;
    
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const positionsArray = pointsRef.current.geometry.attributes.position.array as Float32Array;
    const speed = activity === 'busy' || activity === 'coding' ? 0.5 : 0.2;
    
    for (let i = 0; i < count; i++) {
      phases[i] += delta * speed;
      let r = Math.sqrt(
        positionsArray[i*3]**2 + 
        positionsArray[i*3+1]**2 + 
        positionsArray[i*3+2]**2
      );
      r += delta * speed * 0.5;
      
      if (r > 2.0) r = 1.0;
      
      const norm = Math.sqrt(positions[i*3]**2 + positions[i*3+1]**2 + positions[i*3+2]**2);
      positionsArray[i*3] = (positions[i*3] / norm) * r;
      positionsArray[i*3+1] = (positions[i*3+1] / norm) * r;
      positionsArray[i*3+2] = (positions[i*3+2] / norm) * r;
    }
    pointsRef.current.geometry.attributes.position.needsUpdate = true;
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
        />
      </bufferGeometry>
      <pointsMaterial
        ref={materialRef}
        size={0.05}
        color={targetColor}
        transparent
        opacity={opacity * 0.6}
        blending={THREE.AdditiveBlending}
        depthWrite={false}
      />
    </points>
  );
});
BrainParticles.displayName = 'BrainParticles';

const ElectricSynapses = React.memo(({ count, activity, opacity }: { count: number, activity: string, opacity: number }) => {
  const pointsRef = useRef<THREE.Points>(null);
  
  const [positions, offsets] = useMemo(() => {
    const pos = new Float32Array(count * 3);
    const offs = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      offs[i] = Math.random() * Math.PI * 2;
      pos[i * 3] = 0;
      pos[i * 3 + 1] = 0;
      pos[i * 3 + 2] = 0;
    }
    return [pos, offs];
  }, [count]);

  useFrame((state, delta) => {
    if (!pointsRef.current || activity === 'offline' || activity === 'disconnected') return;
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const positionsArray = pointsRef.current.geometry.attributes.position.array as Float32Array;
    const speed = activity === 'coding' ? 3 : (activity === 'busy' ? 2 : 1);
    
    for (let i = 0; i < count; i++) {
      offsets[i] += delta * speed;
      const t = offsets[i];
      
      const isLeft = i % 2 === 0;
      const xSign = isLeft ? -1 : 1;
      
      const phi = (Math.sin(t * 0.5) * 0.5 + 0.5) * Math.PI;
      const theta = t * 2.0;
      
      let x = Math.sin(phi) * Math.cos(theta);
      let y = Math.cos(phi);
      let z = Math.sin(phi) * Math.sin(theta);
      
      y *= 0.8;
      z *= 1.2;
      
      if (isLeft && x > 0) x *= 0.2;
      if (!isLeft && x < 0) x *= 0.2;
      
      x += xSign * 0.4;
      y += 0.5;
      
      // Bump outwards slightly to float on surface
      positionsArray[i * 3] = x * 1.05;
      positionsArray[i * 3 + 1] = y * 1.05;
      positionsArray[i * 3 + 2] = z * 1.05;
    }
    pointsRef.current.geometry.attributes.position.needsUpdate = true;
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.08}
        color={0xffffff}
        transparent
        opacity={opacity * 0.9}
        blending={THREE.AdditiveBlending}
        depthWrite={false}
      />
    </points>
  );
});
ElectricSynapses.displayName = 'ElectricSynapses';


export const HolographicBrain = ({
  position = [0, 0, 0],
  scale = 1,
  color = '#00f0ff',
  pulseSpeed = 1,
  pulseIntensity = 1,
  activity = 'idle',
  isCentral = true,
  opacity = 1,
  onClick
}: HolographicBrainProps) => {
  const groupRef = useRef<THREE.Group>(null);
  
  const targetColorHex = getActivityColor(activity, color);
  const targetColor = useMemo(() => new THREE.Color(targetColorHex), [targetColorHex]);
  
  const isOffline = activity === 'offline' || activity === 'disconnected';
  const targetOpacity = activity === 'disconnected' ? 0.1 : opacity;

  const [reduceMotion, setReduceMotion] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReduceMotion(mq.matches);
    const handler = (e: MediaQueryListEvent) => setReduceMotion(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const sharedMaterialRef = useRef<THREE.MeshStandardMaterial>(null);
  const glowMaterialRef = useRef<THREE.MeshBasicMaterial>(null);

  useFrame((state, delta) => {
    if (sharedMaterialRef.current) {
      sharedMaterialRef.current.color.lerp(targetColor, delta * 3);
      sharedMaterialRef.current.emissive.lerp(targetColor, delta * 3);
    }
    if (glowMaterialRef.current) {
      glowMaterialRef.current.color.lerp(targetColor, delta * 3);
    }

    if (!groupRef.current) return;
    
    if (!reduceMotion && !isOffline) {
      let speedMult = 1;
      let scaleOscillation = 0.02;
      
      switch (activity) {
        case 'busy': speedMult = 3; scaleOscillation = 0.05; break;
        case 'coding': speedMult = 2.5; scaleOscillation = 0.04; break;
        case 'reasoning': speedMult = 1.5; scaleOscillation = 0.03; break;
        case 'searching': speedMult = 2; scaleOscillation = 0.02; break;
        case 'thinking': speedMult = 0.8; scaleOscillation = 0.01; break;
        default: speedMult = 0.5; scaleOscillation = 0.01; break;
      }
      
      const breathe = Math.sin(state.clock.elapsedTime * pulseSpeed * speedMult) * scaleOscillation * pulseIntensity;
      const currentScale = scale + breathe;
      groupRef.current.scale.setScalar(currentScale);
      
      if (activity === 'searching') {
        groupRef.current.rotation.y += delta * 1.5;
      } else {
        groupRef.current.rotation.y += delta * 0.2 * speedMult;
      }
    } else {
      groupRef.current.scale.setScalar(scale);
    }
  });

  const sharedMaterial = useMemo(() => new THREE.MeshStandardMaterial({
    color: targetColorHex,
    emissive: targetColorHex,
    emissiveIntensity: isOffline ? 0 : 0.5 * pulseIntensity,
    transparent: true,
    opacity: isOffline ? targetOpacity * 0.5 : targetOpacity * 0.8,
    wireframe: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  }), [isOffline, targetOpacity, pulseIntensity, targetColorHex]);

  const leftHemisphereGeo = useMemo(() => createHemisphereGeometry(true), []);
  const rightHemisphereGeo = useMemo(() => createHemisphereGeometry(false), []);

  return (
    <group ref={groupRef} position={position} onClick={onClick}>
      <mesh geometry={leftHemisphereGeo} position={[-0.4, 0.5, 0]}>
        <primitive object={sharedMaterial} ref={sharedMaterialRef} attach="material" />
      </mesh>
      <mesh geometry={rightHemisphereGeo} position={[0.4, 0.5, 0]}>
        <primitive object={sharedMaterial} attach="material" />
      </mesh>
      
      {/* Corpus Callosum */}
      <mesh position={[0, 0.5, 0]}>
        <boxGeometry args={[0.8, 0.4, 1.2]} />
        <meshBasicMaterial 
          ref={glowMaterialRef}
          color={targetColorHex} 
          transparent 
          opacity={isOffline ? 0 : 0.4 * targetOpacity} 
          blending={THREE.AdditiveBlending} 
          depthWrite={false} 
        />
      </mesh>
      
      {/* Cerebellum */}
      <mesh position={[0, -0.2, -0.6]}>
        <sphereGeometry args={[0.4, 16, 16]} />
        <primitive object={sharedMaterial} attach="material" />
      </mesh>
      
      {/* Brainstem */}
      <mesh position={[0, -0.8, -0.2]}>
        <cylinderGeometry args={[0.15, 0.1, 0.8, 16]} />
        <primitive object={sharedMaterial} attach="material" />
      </mesh>

      {/* Inner Glow Sphere */}
      <Sphere args={[0.7, 32, 32]} position={[0, 0.4, 0]}>
        <meshBasicMaterial 
          color={targetColorHex} 
          transparent 
          opacity={isOffline ? 0 : 0.15 * targetOpacity} 
          blending={THREE.AdditiveBlending} 
          depthWrite={false} 
        />
      </Sphere>

      {/* Outer Volumetric Glow */}
      <Sphere args={[1.4, 32, 32]} position={[0, 0.4, 0]}>
        <meshBasicMaterial 
          color={targetColorHex} 
          transparent 
          opacity={isOffline ? 0 : 0.05 * targetOpacity} 
          blending={THREE.AdditiveBlending} 
          depthWrite={false} 
          side={THREE.BackSide}
        />
      </Sphere>
      
      {!isOffline && (
        <OrbitalRings 
          count={isCentral ? 3 : 1} 
          targetColor={targetColor} 
          opacity={targetOpacity * 0.3} 
          speedMultiplier={activity === 'busy' || activity === 'coding' ? 2 : 1}
        />
      )}
      
      <BrainParticles 
        count={isCentral ? 150 : 80} 
        targetColor={targetColor} 
        activity={activity} 
        opacity={targetOpacity}
      />
      
      {!isOffline && (
        <ElectricSynapses 
          count={isCentral ? 30 : 15} 
          activity={activity} 
          opacity={targetOpacity}
        />
      )}
    </group>
  );
};

export default HolographicBrain;
