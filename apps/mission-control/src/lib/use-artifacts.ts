import { create } from "zustand";

export interface Artifact {
  id: string;
  messageId: string;
  title: string;
  type: "react" | "html" | "mermaid" | "markdown" | "diff";
  content: string;
  language: string;
  status: "streaming" | "ready" | "error";
  version: number;
  timestamp: string;
  filePath?: string;
}

export interface ConsoleLogEntry {
  type: "log" | "warn" | "error";
  message: string;
  timestamp: string;
}

interface ArtifactState {
  artifacts: Record<string, Artifact>;
  activeArtifactId: string | null;
  consoleLogs: Record<string, ConsoleLogEntry[]>;
  isOpen: boolean;

  // Actions
  registerArtifact: (artifact: Artifact) => void;
  setActiveArtifactId: (id: string | null) => void;
  setIsOpen: (open: boolean) => void;
  updateArtifactContent: (id: string, newContent: string) => void;
  addConsoleLog: (artifactId: string, entry: Omit<ConsoleLogEntry, "timestamp">) => void;
  clearConsoleLogs: (artifactId: string) => void;
  getActiveArtifact: () => Artifact | null;
  getArtifactList: () => Artifact[];
}

export const useArtifactStore = create<ArtifactState>((set, get) => ({
  artifacts: {},
  activeArtifactId: null,
  consoleLogs: {},
  isOpen: false,

  registerArtifact: (artifact) =>
    set((state) => {
      const existing = state.artifacts[artifact.id];
      const version = existing ? existing.version + 1 : (artifact.version || 1);
      const updatedArtifact = { ...artifact, version };
      return {
        artifacts: { ...state.artifacts, [artifact.id]: updatedArtifact },
        activeArtifactId: artifact.id,
        isOpen: true,
      };
    }),

  setActiveArtifactId: (id) =>
    set((state) => ({
      activeArtifactId: id,
      isOpen: id !== null,
    })),

  setIsOpen: (isOpen) => set({ isOpen }),

  updateArtifactContent: (id, newContent) =>
    set((state) => {
      const existing = state.artifacts[id];
      if (!existing) return state;
      const updated: Artifact = {
        ...existing,
        content: newContent,
        version: existing.version + 1,
        timestamp: new Date().toISOString(),
      };
      return {
        artifacts: { ...state.artifacts, [id]: updated },
      };
    }),

  addConsoleLog: (artifactId, entry) =>
    set((state) => {
      const current = state.consoleLogs[artifactId] || [];
      const newEntry: ConsoleLogEntry = {
        ...entry,
        timestamp: new Date().toLocaleTimeString(),
      };
      return {
        consoleLogs: {
          ...state.consoleLogs,
          [artifactId]: [...current.slice(-99), newEntry],
        },
      };
    }),

  clearConsoleLogs: (artifactId) =>
    set((state) => ({
      consoleLogs: {
        ...state.consoleLogs,
        [artifactId]: [],
      },
    })),

  getActiveArtifact: () => {
    const { artifacts, activeArtifactId } = get();
    return activeArtifactId ? artifacts[activeArtifactId] || null : null;
  },

  getArtifactList: () => {
    return Object.values(get().artifacts).sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    );
  },
}));

/**
 * Parses markdown text to detect and extract code blocks as isolated Artifacts.
 * Supports:
 *   ```tsx artifact="Dashboard" title="User Management"
 *   ```html artifact="Preview"
 *   ```mermaid
 *   ```tsx / ```jsx / ```html
 */
export function parseArtifactsFromMarkdown(
  text: string,
  messageId: string = `msg-${Date.now()}`
): Artifact[] {
  const artifacts: Artifact[] = [];
  const fenceRegex = /```(\w+)(?:[^\n]*?)?\n([\s\S]*?)```/g;

  let match: RegExpExecArray | null;
  let index = 0;

  while ((match = fenceRegex.exec(text)) !== null) {
    index++;
    const rawHeader = match[0].split("\n")[0];
    const language = (match[1] || "text").toLowerCase();
    const content = match[2].trim();

    if (language !== "mermaid" && content.split("\n").length < 3 && content.length < 40) {
      continue;
    }

    const artifactAttrMatch = rawHeader.match(/artifact=["']([^"']+)["']/i);
    const titleAttrMatch = rawHeader.match(/title=["']([^"']+)["']/i);
    const fileAttrMatch = rawHeader.match(/file=["']([^"']+)["']/i);

    let type: Artifact["type"] = "markdown";
    if (["tsx", "jsx", "react"].includes(language)) {
      type = "react";
    } else if (["html", "htm", "svg"].includes(language)) {
      type = "html";
    } else if (language === "mermaid") {
      type = "mermaid";
    } else if (["diff", "patch"].includes(language)) {
      type = "diff";
    } else if (["ts", "js", "python", "py", "json", "yaml", "css"].includes(language)) {
      if (content.includes("export default") || content.includes("return (") || content.includes("React.")) {
        type = "react";
      } else {
        type = "markdown";
      }
    }

    let title =
      titleAttrMatch?.[1] ||
      artifactAttrMatch?.[1] ||
      fileAttrMatch?.[1];

    if (!title) {
      const compMatch = content.match(/(?:function|const|class)\s+([A-Z][A-Za-z0-9_]+)/);
      if (compMatch) {
        title = `${compMatch[1]}.${type === "react" ? "tsx" : "js"}`;
      } else if (type === "mermaid") {
        title = "Architecture Diagram";
      } else if (type === "html") {
        title = "HTML Preview";
      } else {
        title = `Artifact ${index}`;
      }
    }

    const artifactId = `art-${messageId}-${index}`;

    artifacts.push({
      id: artifactId,
      messageId,
      title,
      type,
      content,
      language,
      status: "ready",
      version: 1,
      timestamp: new Date().toISOString(),
      filePath: fileAttrMatch?.[1] || (type === "react" ? `src/components/${title}` : undefined),
    });
  }

  return artifacts;
}
