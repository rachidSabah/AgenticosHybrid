"use client";

import React, { useRef, useMemo, useEffect, useState } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mediaQuery.matches);
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches);
    mediaQuery.addEventListener("change", handler);
    return () => mediaQuery.removeEventListener("change", handler);
  }, []);
  return reduced;
}

const starVertexShader = `
  attribute float size;
  attribute vec3 customColor;
  attribute float phase;
  
  varying vec3 vColor;
  varying float vPhase;
  
  void main() {
    vColor = customColor;
    vPhase = phase;
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = size * (300.0 / -mvPosition.z);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const starFragmentShader = `
  uniform float time;
  uniform bool reducedMotion;
  
  varying vec3 vColor;
  varying float vPhase;
  
  void main() {
    float alpha = 1.0;
    if (!reducedMotion) {
      alpha = 0.5 + 0.5 * sin(time * 2.0 + vPhase);
    }
    
    // Circular point
    vec2 pt = gl_PointCoord - vec2(0.5);
    if (dot(pt, pt) > 0.25) discard;
    
    gl_FragColor = vec4(vColor, alpha * 0.8);
  }
`;

function DataStreams({ count = 300 }: { count?: number }) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const reducedMotion = useReducedMotion();
  
  const dummy = useMemo(() => new THREE.Object3D(), []);
  
  const particles = useMemo(() => {
    const temp = [];
    for (let i = 0; i < count; i++) {
      const x = (Math.random() - 0.5) * 80;
      const y = (Math.random() - 0.5) * 60;
      const z = (Math.random() - 0.5) * 80;
      const speed = 1 + Math.random() * 3;
      temp.push({ x, y, z, speed });
    }
    return temp;
  }, [count]);
  
  useEffect(() => {
    if (!meshRef.current) return;
    particles.forEach((p, i) => {
      dummy.position.set(p.x, p.y, p.z);
      dummy.updateMatrix();
      meshRef.current!.setMatrixAt(i, dummy.matrix);
    });
    meshRef.current.instanceMatrix.needsUpdate = true;
  }, [particles, dummy]);
  
  useFrame((state, delta) => {
    if (reducedMotion || !meshRef.current) return;
    
    particles.forEach((p, i) => {
      p.y -= p.speed * delta;
      if (p.y < -30) p.y = 30;
      dummy.position.set(p.x, p.y, p.z);
      dummy.updateMatrix();
      meshRef.current!.setMatrixAt(i, dummy.matrix);
    });
    meshRef.current.instanceMatrix.needsUpdate = true;
  });
  
  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, count]}>
      <sphereGeometry args={[0.08, 8, 8]} />
      <meshBasicMaterial color="#00f0ff" transparent opacity={0.6} blending={THREE.AdditiveBlending} depthWrite={false} />
    </instancedMesh>
  );
}

export function StarFieldBackground() {
  const pointsRef = useRef<THREE.Points>(null);
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const reducedMotion = useReducedMotion();
  
  const starCount = 2000;
  
  const [positions, colors, sizes, phases] = useMemo(() => {
    const positions = new Float32Array(starCount * 3);
    const colors = new Float32Array(starCount * 3);
    const sizes = new Float32Array(starCount);
    const phases = new Float32Array(starCount);
    
    const colorChoices = [
      new THREE.Color("#e0f7fa"), // light cyan
      new THREE.Color("#b3e5fc"), // light blue
      new THREE.Color("#ffffff"), // white
      new THREE.Color("#818cf8"), // electric blue
    ];
    
    for (let i = 0; i < starCount; i++) {
      // Spherical distribution
      const r = 80 + Math.random() * 40;
      const theta = 2 * Math.PI * Math.random();
      const phi = Math.acos(2 * Math.random() - 1);
      
      positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      positions[i * 3 + 2] = r * Math.cos(phi);
      
      const color = colorChoices[Math.floor(Math.random() * colorChoices.length)];
      colors[i * 3] = color.r;
      colors[i * 3 + 1] = color.g;
      colors[i * 3 + 2] = color.b;
      
      sizes[i] = 0.03 + Math.random() * 0.09;
      phases[i] = Math.random() * Math.PI * 2;
    }
    
    return [positions, colors, sizes, phases];
  }, [starCount]);

  useFrame((state, delta) => {
    if (materialRef.current) {
      materialRef.current.uniforms.time.value = state.clock.elapsedTime;
      materialRef.current.uniforms.reducedMotion.value = reducedMotion;
    }
    
    if (!reducedMotion && pointsRef.current) {
      pointsRef.current.rotation.y += delta * 0.02;
      pointsRef.current.rotation.x += delta * 0.005;
    }
  });

  return (
    <group>
      {/* Star Field */}
      <points ref={pointsRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
          <bufferAttribute attach="attributes-customColor" args={[colors, 3]} />
          <bufferAttribute attach="attributes-size" args={[sizes, 1]} />
          <bufferAttribute attach="attributes-phase" args={[phases, 1]} />
        </bufferGeometry>
        <shaderMaterial
          ref={materialRef}
          vertexShader={starVertexShader}
          fragmentShader={starFragmentShader}
          uniforms={{
            time: { value: 0 },
            reducedMotion: { value: false }
          }}
          transparent
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </points>

      {/* Hex Grid Floor */}
      <gridHelper args={[200, 100, "#1f2937", "#111827"]} position={[0, -6.5, 0]} />

      {/* Digital Fog / Volumetric Light */}
      <pointLight position={[0, -5, -20]} distance={50} intensity={0.5} color="#00f0ff" />
      <fog attach="fog" args={["#060810", 10, 100]} />

      {/* Nebula Clouds */}
      <mesh position={[-30, 20, -60]}>
        <sphereGeometry args={[40, 32, 32]} />
        <meshBasicMaterial color="#4f6cff" transparent opacity={0.15} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh position={[40, -10, -50]}>
        <sphereGeometry args={[35, 32, 32]} />
        <meshBasicMaterial color="#a855f7" transparent opacity={0.15} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      
      {/* Data Streams */}
      <DataStreams count={300} />
    </group>
  );
}
