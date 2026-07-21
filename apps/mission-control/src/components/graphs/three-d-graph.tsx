"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass";
import { type Node, type Edge } from "reactflow";

interface ThreeDGraphProps {
  nodes: Node[];
  edges: Edge[];
  onNodeClick?: (id: string) => void;
}

const STATUS_COLORS: Record<string, string> = {
  running: "#10b981",
  completed: "#3b82f6",
  failed: "#ef4444",
  idle: "#64748b",
  healthy: "#10b981",
  degraded: "#f59e0b",
  down: "#ef4444",
  thinking: "#8b5cf6",
  coding: "#06b6d4",
};

export function ThreeDGraph({ nodes, edges, onNodeClick }: ThreeDGraphProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

  useEffect(() => {
    if (!mountRef.current) return;

    // Scene setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x080a10);
    scene.fog = new THREE.Fog(0x080a10, 5, 15);

    const camera = new THREE.PerspectiveCamera(75, mountRef.current.clientWidth / mountRef.current.clientHeight, 0.1, 1000);
    camera.position.set(0, 0, 10);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(mountRef.current.clientWidth, mountRef.current.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    mountRef.current.appendChild(renderer.domElement);

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.screenSpacePanning = false;
    controls.minDistance = 5;
    controls.maxDistance = 20;

    // Post-processing for glow effect
    const renderScene = new RenderPass(scene, camera);
    const bloomPass = new UnrealBloomPass(
      new THREE.Vector2(mountRef.current.clientWidth, mountRef.current.clientHeight),
      1.5, 0.4, 0.85
    );
    bloomPass.threshold = 0;
    bloomPass.strength = 1.5;
    bloomPass.radius = 0.8;

    const composer = new EffectComposer(renderer);
    composer.addPass(renderScene);
    composer.addPass(bloomPass);

    // Create nodes
    const nodeMeshes: Record<string, THREE.Mesh> = {};
    const nodeGroup = new THREE.Group();
    scene.add(nodeGroup);

    nodes.forEach((node) => {
      const color = new THREE.Color(STATUS_COLORS[node.data?.status || "idle"]);
      const geometry = new THREE.SphereGeometry(0.5, 32, 32);
      const material = new THREE.MeshStandardMaterial({
        color,
        emissive: color,
        emissiveIntensity: 0.5,
        metalness: 0.2,
        roughness: 0.4,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.set(
        Math.random() * 8 - 4,
        Math.random() * 8 - 4,
        Math.random() * 8 - 4
      );
      mesh.userData = { id: node.id, node };
      nodeGroup.add(mesh);
      nodeMeshes[node.id] = mesh;
    });

    // Create edges
    const edgeGroup = new THREE.Group();
    scene.add(edgeGroup);

    edges.forEach((edge) => {
      const sourceNode = nodes.find((n) => n.id === edge.source);
      const targetNode = nodes.find((n) => n.id === edge.target);
      if (!sourceNode || !targetNode) return;

      const sourceMesh = nodeMeshes[edge.source];
      const targetMesh = nodeMeshes[edge.target];
      if (!sourceMesh || !targetMesh) return;

      const color = new THREE.Color(0x6366f1);
      const material = new THREE.LineBasicMaterial({
        color,
        transparent: true,
        opacity: 0.3,
      });

      const points = [
        new THREE.Vector3(sourceMesh.position.x, sourceMesh.position.y, sourceMesh.position.z),
        new THREE.Vector3(targetMesh.position.x, targetMesh.position.y, targetMesh.position.z),
      ];
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      const line = new THREE.Line(geometry, material);
      edgeGroup.add(line);
    });

    // Lights
    const ambientLight = new THREE.AmbientLight(0x404040, 0.5);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(1, 1, 1);
    scene.add(directionalLight);

    // Animation loop
    const animate = () => {
      requestAnimationFrame(animate);
      controls.update();
      composer.render();
    };
    animate();

    // Handle window resize
    const handleResize = () => {
      camera.aspect = mountRef.current!.clientWidth / mountRef.current!.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(mountRef.current!.clientWidth, mountRef.current!.clientHeight);
      composer.setSize(mountRef.current!.clientWidth, mountRef.current!.clientHeight);
    };
    window.addEventListener("resize", handleResize);

    // Raycaster for node selection
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const onMouseClick = (event: MouseEvent) => {
      if (!mountRef.current) return;

      // Calculate mouse position in normalized device coordinates
      const rect = mountRef.current.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      // Update the raycaster
      raycaster.setFromCamera(mouse, camera);

      // Check for intersections
      const intersects = raycaster.intersectObjects(nodeGroup.children);
      if (intersects.length > 0) {
        const object = intersects[0].object;
        const nodeId = object.userData.id;
        setSelectedNode(nodeId);
        onNodeClick?.(nodeId);
      }
    };
    mountRef.current.addEventListener("click", onMouseClick);

    // Cleanup
    return () => {
      window.removeEventListener("resize", handleResize);
      if (mountRef.current) {
        mountRef.current.removeEventListener("click", onMouseClick);
        mountRef.current.removeChild(renderer.domElement);
      }
    };
  }, [nodes, edges, onNodeClick]);

  return <div ref={mountRef} className="h-full w-full" />;
}