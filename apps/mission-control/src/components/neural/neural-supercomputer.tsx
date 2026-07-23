"use client";

import { AnatomicalAIBrain } from "./anatomical-ai-brain";

interface SupercomputerProps {
  onSelectBrain?: (provider: string | null) => void;
}

export function NeuralSupercomputer({ onSelectBrain }: SupercomputerProps) {
  return <AnatomicalAIBrain onSelectProvider={onSelectBrain} />;
}

export default NeuralSupercomputer;

