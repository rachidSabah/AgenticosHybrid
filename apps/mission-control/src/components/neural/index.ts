/**
 * Neural Intelligence Visualization Components
 * 
 * Barrel export for all shared 3D visualization components used by
 * the AI Brain and Agent Constellation views.
 * 
 * Architecture: React Three Fiber + post-processing + Zustand store
 * Visual DNA: JARVIS / NASA Mission Control / Apple Vision Pro / TRON
 */

export { HolographicBrain } from "./holographic-brain";
export type { HolographicBrainProps } from "./holographic-brain";

export { NeuralLink } from "./neural-link";
export type { NeuralLinkProps } from "./neural-link";

export { TaskPacket } from "./task-packet";
export type { TaskPacketProps } from "./task-packet";

export { StarFieldBackground } from "./star-field";

export { BrainHUD } from "./brain-hud";
export type { BrainHUDProps } from "./brain-hud";

export {
  TelemetryPanel,
  MiniSparkline,
  CircularGauge,
  EventFrequencyMeter,
  ConnectionStatusPanel,
  MissionProgressPanel,
} from "./telemetry-charts";

export {
  ProviderDetailPanel,
  ConnectionDetailPanel,
  TaskDetailPanel,
} from "./detail-panel";
