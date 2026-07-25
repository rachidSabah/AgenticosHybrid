"use client";

import { useMemo, useState, useRef, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ZoomIn, ZoomOut, Maximize2, RefreshCw,
} from "lucide-react";
import type { BrainRecord, BrainRelationship, RelationshipType } from "@/lib/use-brains";
import { brainStatusToColor, VENDOR_ICON_MAP } from "@/lib/use-brains";

// ── Edge color map ──────────────────────────────────────────────────────────

const EDGE_COLORS: Record<string, string> = {
  parent: "#818cf8",
  child: "#818cf8",
  peer: "#94a3b8",
  executor: "#10b981",
  planner: "#f59e0b",
  reviewer: "#f97316",
  observer: "#6366f1",
  fallback: "#ef4444",
  shadow: "#8b5cf6",
  mirror: "#d946ef",
  consensus: "#22d3ee",
  delegation: "#06b6d4",
  communication: "#38bdf8",
  routing: "#0ea5e9",
  tool_usage: "#f43f5e",
  shared_context: "#a855f7",
  execution_chain: "#10b981",
  mcp_connection: "#64748b",
};

function edgeColor(type: RelationshipType | string): string {
  return EDGE_COLORS[type] ?? "#64748b";
}

// ── Layout helpers ──────────────────────────────────────────────────────────

interface LayoutNode {
  id: string;
  x: number;
  y: number;
  radius: number;
  brain: BrainRecord;
}

function computeLayout(
  brains: BrainRecord[],
  width: number,
  height: number,
): LayoutNode[] {
  if (brains.length === 0) return [];

  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(width, height) * 0.35;

  // Sort by priority (highest first) so important brains are more central
  const sorted = [...brains].sort((a, b) => b.priority - a.priority);
  const n = sorted.length;

  return sorted.map((brain, i) => {
    // Core brains (highest priority) get larger and closer to center
    const isCore = i === 0 || brain.brain_type === "orchestrator";
    const r = isCore
      ? radius * 0.15
      : radius;
    const angle = (i / n) * Math.PI * 2 - Math.PI / 2 + (isCore ? 0 : 0.2);
    const jitter = isCore ? 0 : (Math.random() - 0.5) * 20;

    return {
      id: brain.id,
      x: isCore ? centerX : centerX + r * Math.cos(angle) + jitter,
      y: isCore ? centerY : centerY + r * Math.sin(angle) + jitter,
      radius: isCore ? 40 : 28,
      brain,
    };
  });
}

// ── Main Component ──────────────────────────────────────────────────────────

interface BrainConstellationProps {
  brains: BrainRecord[];
  relationships: BrainRelationship[];
  onSelectBrain?: (id: string) => void;
}

export function BrainConstellation({
  brains,
  relationships,
  onSelectBrain,
}: BrainConstellationProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [dim, setDim] = useState({ width: 800, height: 600 });
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 });
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  // Resize observer
  useEffect(() => {
    const el = svgRef.current?.parentElement;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) {
        setDim({ width, height });
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Layout
  const layoutNodes = useMemo(
    () => computeLayout(brains, dim.width, dim.height),
    [brains, dim.width, dim.height],
  );

  const nodeMap = useMemo(() => {
    const map = new Map<string, LayoutNode>();
    for (const n of layoutNodes) map.set(n.id, n);
    return map;
  }, [layoutNodes]);

  const hoveredNodeData = hoveredNode ? nodeMap.get(hoveredNode) : undefined;

  // Edges
  const edges = useMemo(() => {
    return relationships.filter((r) => {
      return nodeMap.has(r.source_id) && nodeMap.has(r.target_id);
    });
  }, [relationships, nodeMap]);

  // ── Zoom / Pan handlers ──

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setTransform((t) => ({
      ...t,
      scale: Math.max(0.2, Math.min(5, t.scale * delta)),
    }));
  }, []);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === svgRef.current || (e.target as SVGElement).tagName === "svg") {
        setIsDragging(true);
        setDragStart({ x: e.clientX - transform.x, y: e.clientY - transform.y });
      }
    },
    [transform.x, transform.y],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (isDragging) {
        setTransform((t) => ({
          ...t,
          x: e.clientX - dragStart.x,
          y: e.clientY - dragStart.y,
        }));
      }
    },
    [isDragging, dragStart],
  );

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  const resetView = useCallback(() => {
    setTransform({ x: 0, y: 0, scale: 1 });
  }, []);

  const zoomIn = useCallback(() => {
    setTransform((t) => ({ ...t, scale: Math.min(5, t.scale * 1.3) }));
  }, []);

  const zoomOut = useCallback(() => {
    setTransform((t) => ({ ...t, scale: Math.max(0.2, t.scale / 1.3) }));
  }, []);

  // ── Edge path ──

  const edgePath = (source: LayoutNode, target: LayoutNode) => {
    const dx = target.x - source.x;
    const dy = target.y - source.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    const curve = Math.min(dist * 0.3, 60);
    const midX = (source.x + target.x) / 2;
    const midY = (source.y + target.y) / 2 - curve;
    return `M ${source.x} ${source.y} Q ${midX} ${midY} ${target.x} ${target.y}`;
  };

  // ── Tooltip for nodes ──

  const tooltipContent = hoveredNodeData
    ? `${hoveredNodeData.brain.display_name} (${hoveredNodeData.brain.status})`
    : null;

  return (
    <div className="relative h-full w-full overflow-hidden rounded-xl border border-border/30 bg-surface/5">
      {/* Toolbar */}
      <div className="absolute top-3 right-3 z-20 flex items-center gap-1 rounded-lg border border-border/30 bg-surface/80 backdrop-blur-sm p-1">
        <button
          onClick={zoomIn}
          className="rounded-md p-1.5 hover:bg-surface/40 transition text-faint hover:text-text"
          title="Zoom in"
        >
          <ZoomIn size={14} />
        </button>
        <button
          onClick={zoomOut}
          className="rounded-md p-1.5 hover:bg-surface/40 transition text-faint hover:text-text"
          title="Zoom out"
        >
          <ZoomOut size={14} />
        </button>
        <button
          onClick={resetView}
          className="rounded-md p-1.5 hover:bg-surface/40 transition text-faint hover:text-text"
          title="Reset view"
        >
          <Maximize2 size={14} />
        </button>
        <span className="text-[10px] text-faint px-1 select-none">
          {Math.round(transform.scale * 100)}%
        </span>
      </div>

      {/* SVG canvas */}
      <svg
        ref={svgRef}
        className="h-full w-full cursor-grab active:cursor-grabbing"
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <defs>
          {/* Glow filter for active edges */}
          <filter id="glow">
            <feGaussianBlur stdDeviation="2" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Pulse animation for executing edges */}
          <style>
            {`
              @keyframes dash-flow {
                to { stroke-dashoffset: -24; }
              }
              @keyframes pulse-node {
                0%, 100% { opacity: 0.6; }
                50% { opacity: 1; }
              }
            `}
          </style>
        </defs>

        <g
          transform={`translate(${transform.x}, ${transform.y}) scale(${transform.scale})`}
        >
          {/* Edges */}
          {edges.map((rel) => {
            const source = nodeMap.get(rel.source_id);
            const target = nodeMap.get(rel.target_id);
            if (!source || !target) return null;

            const color = edgeColor(rel.relationship_type);
            const isHovered = hoveredEdge === rel.id;
            const isExecuting = rel.relationship_type === "execution_chain" || rel.relationship_type === "routing";
            const strokeWidth = Math.max(1, rel.weight * 3);

            return (
              <g
                key={rel.id}
                onMouseEnter={() => setHoveredEdge(rel.id)}
                onMouseLeave={() => setHoveredEdge(null)}
                style={{ cursor: "pointer" }}
              >
                {/* Edge line */}
                <path
                  d={edgePath(source, target)}
                  fill="none"
                  stroke={color}
                  strokeWidth={isHovered ? strokeWidth + 1 : strokeWidth}
                  strokeOpacity={isHovered ? 0.9 : 0.4}
                  strokeDasharray={isExecuting ? "4 4" : "none"}
                  style={
                    isExecuting && rel.active
                      ? { animation: "dash-flow 1s linear infinite" }
                      : undefined
                  }
                  filter={isHovered ? "url(#glow)" : undefined}
                />

                {/* Arrow marker on hover */}
                {isHovered && (
                  <circle
                    cx={(source.x + target.x) / 2}
                    cy={(source.y + target.y) / 2}
                    r={3}
                    fill={color}
                  />
                )}

                {/* Edge label on hover */}
                {isHovered && (
                  <text
                    x={(source.x + target.x) / 2}
                    y={(source.y + target.y) / 2 - 10}
                    textAnchor="middle"
                    fill={color}
                    fontSize="8"
                    fontFamily="monospace"
                  >
                    {rel.relationship_type} ({(rel.weight * 100).toFixed(0)}%)
                  </text>
                )}
              </g>
            );
          })}

          {/* Nodes */}
          {layoutNodes.map((node) => {
            const color = brainStatusToColor(node.brain.status);
            const isHovered = hoveredNode === node.id;
            const isCore = node.brain.brain_type === "orchestrator" || node.radius >= 40;

            return (
              <g
                key={node.id}
                transform={`translate(${node.x}, ${node.y})`}
                onMouseEnter={() => setHoveredNode(node.id)}
                onMouseLeave={() => setHoveredNode(null)}
                onClick={() => onSelectBrain?.(node.id)}
                style={{ cursor: "pointer" }}
              >
                {/* Pulse ring for active brains */}
                {["connected", "executing", "busy"].includes(node.brain.status) && (
                  <circle
                    r={node.radius + 6}
                    fill="none"
                    stroke={color}
                    strokeWidth={1.5}
                    strokeOpacity={0.4}
                    style={{ animation: "pulse-node 2s ease-in-out infinite" }}
                  />
                )}

                {/* Outer ring */}
                <circle
                  r={node.radius}
                  fill={`${color}15`}
                  stroke={isHovered ? color : `${color}66`}
                  strokeWidth={isHovered ? 2.5 : 1.5}
                  filter={isHovered ? "url(#glow)" : undefined}
                />

                {/* Inner circle */}
                <circle
                  r={node.radius * 0.5}
                  fill={`${color}30`}
                  stroke={color}
                  strokeWidth={1}
                />

                {/* Vendor initial */}
                <text
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill={color}
                  fontSize={node.radius * 0.5}
                  fontFamily="monospace"
                  fontWeight="bold"
                >
                  {node.brain.vendor.charAt(0).toUpperCase()}
                </text>

                {/* Brain label below */}
                <text
                  y={node.radius + 14}
                  textAnchor="middle"
                  fill={isHovered ? "#e2e8f0" : "#94a3b8"}
                  fontSize={isCore ? "9" : "8"}
                  fontFamily="sans-serif"
                  fontWeight={isCore ? "bold" : "normal"}
                >
                  {node.brain.display_name.length > 14
                    ? node.brain.display_name.slice(0, 14) + "…"
                    : node.brain.display_name}
                </text>

                {/* Status badge */}
                <text
                  y={node.radius + 26}
                  textAnchor="middle"
                  fill={color}
                  fontSize="7"
                  fontFamily="monospace"
                  opacity={0.8}
                >
                  {node.brain.status}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      {/* Legend */}
      <div className="absolute bottom-3 left-3 z-20 rounded-lg border border-border/30 bg-surface/80 backdrop-blur-sm p-2.5 text-[9px]">
        <div className="text-faint font-medium mb-1.5 uppercase tracking-wider">Legend</div>
        <div className="space-y-1">
          {[
            { type: "executor", label: "Executor" },
            { type: "routing", label: "Routing" },
            { type: "communication", label: "Communication" },
            { type: "consensus", label: "Consensus" },
            { type: "peer", label: "Peer" },
            { type: "parent", label: "Parent/Child" },
          ].map(({ type, label }) => (
            <div key={type} className="flex items-center gap-2 text-faint">
              <span
                className="inline-block h-0.5 w-4"
                style={{ backgroundColor: edgeColor(type) }}
              />
              <span>{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Hover tooltip */}
      <AnimatePresence>
        {hoveredNode && hoveredNodeData && (
          <motion.div
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 5 }}
            className="absolute top-3 left-3 z-30 rounded-lg border border-border/30 bg-surface/90 backdrop-blur-md px-3 py-2 text-xs shadow-xl pointer-events-none"
          >
            <div className="font-semibold text-text">{hoveredNodeData.brain.display_name}</div>
            <div className="text-faint mt-0.5 space-y-0.5">
              <div>{hoveredNodeData.brain.brain_type} · {hoveredNodeData.brain.vendor}</div>
              <div className="flex items-center gap-2">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ backgroundColor: brainStatusToColor(hoveredNodeData.brain.status) }}
                />
                <span>{hoveredNodeData.brain.status}</span>
                <span>CPU: {hoveredNodeData.brain.cpu_usage.toFixed(0)}%</span>
                <span>RAM: {(hoveredNodeData.brain.memory_usage / 1024).toFixed(1)}GB</span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
