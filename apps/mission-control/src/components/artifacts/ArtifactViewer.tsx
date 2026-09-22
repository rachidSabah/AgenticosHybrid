"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Artifact,
  ConsoleLogEntry,
  useArtifactStore,
} from "@/lib/use-artifacts";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/primitives";
import {
  Code,
  Eye,
  Terminal,
  ExternalLink,
  Copy,
  Check,
  Download,
  X,
  RefreshCw,
  AlertTriangle,
  ChevronRight,
  FileCode,
  FileCheck,
  Sparkles,
  Layers,
  Save,
} from "lucide-react";

interface ArtifactViewerProps {
  artifact: Artifact | null;
  onClose?: () => void;
  className?: string;
}

const EMPTY_LOGS: ConsoleLogEntry[] = [];

export function ArtifactViewer({ artifact, onClose, className = "" }: ArtifactViewerProps) {
  const [mode, setMode] = useState<"preview" | "code" | "console">("preview");
  const [copied, setCopied] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applyResult, setApplyResult] = useState<string | null>(null);
  const [customPath, setCustomPath] = useState<string>("");
  const [showPathInput, setShowPathInput] = useState(false);
  const [iframeKey, setIframeKey] = useState(0);

  const allConsoleLogs = useArtifactStore((s) => s.consoleLogs);
  const consoleLogs = artifact && allConsoleLogs[artifact.id] ? allConsoleLogs[artifact.id] : EMPTY_LOGS;
  const addConsoleLog = useArtifactStore((s) => s.addConsoleLog);
  const clearConsoleLogs = useArtifactStore((s) => s.clearConsoleLogs);

  useEffect(() => {
    if (artifact?.filePath) {
      setCustomPath(artifact.filePath);
    } else if (artifact) {
      setCustomPath(`src/components/${artifact.title}`);
    }
  }, [artifact]);

  // Listen to postMessage from sandboxed iframe for console logs and errors
  useEffect(() => {
    const handleMessage = (e: MessageEvent) => {
      if (!e.data || e.data.source !== "artifact-sandbox") return;
      if (!artifact) return;

      if (e.data.type === "log" || e.data.type === "warn" || e.data.type === "error") {
        addConsoleLog(artifact.id, {
          type: e.data.type,
          message: typeof e.data.payload === "string" ? e.data.payload : JSON.stringify(e.data.payload),
        });
      }
    };

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [artifact, addConsoleLog]);

  const handleCopy = async () => {
    if (!artifact) return;
    try {
      await navigator.clipboard.writeText(artifact.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  const handleApplyToWorkspace = async () => {
    if (!artifact || applying) return;
    const targetPath = customPath.trim() || artifact.filePath || `src/components/${artifact.title}`;
    setApplying(true);
    setApplyResult(null);
    try {
      const res = await api.workspaceApplyArtifact({
        file_path: targetPath,
        content: artifact.content,
        create_backup: true,
      });
      if (res && res.success) {
        setApplyResult(`Saved to ${targetPath}`);
        setTimeout(() => setApplyResult(null), 4000);
        setShowPathInput(false);
      } else {
        setApplyResult("Failed to write file");
      }
    } catch (err: any) {
      setApplyResult(`Error: ${err.message || "Failed to save"}`);
    } finally {
      setApplying(false);
    }
  };

  const handlePopOut = () => {
    if (!artifact) return;
    const blob = new Blob([srcDocContent], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
  };

  // Generate safe sandboxed HTML for iframe
  const srcDocContent = useMemo(() => {
    if (!artifact) return "";

    const consoleHookScript = `
      <script>
        (function() {
          const originalLog = console.log;
          const originalWarn = console.warn;
          const originalError = console.error;
          
          function formatArg(arg) {
            if (arg === null) return "null";
            if (arg === undefined) return "undefined";
            if (typeof arg === "object") {
              try { return JSON.stringify(arg); } catch(e) { return String(arg); }
            }
            return String(arg);
          }

          console.log = function(...args) {
            originalLog.apply(console, args);
            const msg = args.map(formatArg).join(" ");
            if (msg.includes("in-browser Babel transformer") || msg.includes("babeljs.io")) return;
            window.parent.postMessage({
              source: "artifact-sandbox",
              type: "log",
              payload: msg
            }, "*");
          };

          console.warn = function(...args) {
            originalWarn.apply(console, args);
            const msg = args.map(formatArg).join(" ");
            if (msg.includes("in-browser Babel transformer") || msg.includes("babeljs.io")) return;
            window.parent.postMessage({
              source: "artifact-sandbox",
              type: "warn",
              payload: msg
            }, "*");
          };

          console.error = function(...args) {
            originalError.apply(console, args);
            window.parent.postMessage({
              source: "artifact-sandbox",
              type: "error",
              payload: args.map(formatArg).join(" ")
            }, "*");
          };

          window.onerror = function(message, source, lineno, colno, error) {
            window.parent.postMessage({
              source: "artifact-sandbox",
              type: "error",
              payload: message + " (Line " + lineno + ")"
            }, "*");
            const errBox = document.getElementById("__runtime_error_box__");
            if (errBox) {
              errBox.style.display = "block";
              errBox.innerHTML = '<div style="padding: 16px; background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.4); border-radius: 12px; color: #fca5a5; font-family: monospace; font-size: 12px;"><strong style="color: #ef4444;">Runtime Error:</strong><br/>' + message + ' (Line ' + lineno + ')</div>';
            }
            return false;
          };
        })();
      </script>
    `;

    // 1. React / TSX Preview
    if (artifact.type === "react") {
      let codeToTransform = artifact.content;

      // Extract any imported icon names from "lucide-react", "@heroicons", etc.
      const iconNames = new Set<string>();
      const importIconRegex = /import\s+\{([^}]+)\}\s+from\s+['"](?:lucide-react|react-feather|@heroicons\/[^'"]+)['"]/g;
      let iconMatch: RegExpExecArray | null;
      while ((iconMatch = importIconRegex.exec(codeToTransform)) !== null) {
        iconMatch[1].split(",").forEach((n) => {
          const trimmed = n.trim().split(/\s+as\s+/)[0].trim();
          if (trimmed && /^[A-Z]/.test(trimmed)) iconNames.add(trimmed);
        });
      }

      // Strip all import statements cleanly
      codeToTransform = codeToTransform
        .replace(/import\s+[\s\S]*?from\s+['"].*?['"];?/g, "")
        .replace(/import\s+['"].*?['"];?/g, "");

      // Identify component name from export default
      let identifiedComponentName = "";
      const defaultFnMatch = codeToTransform.match(/export\s+default\s+function\s+([A-Za-z0-9_]+)/);
      const defaultClassMatch = codeToTransform.match(/export\s+default\s+class\s+([A-Za-z0-9_]+)/);
      const defaultVarMatch = codeToTransform.match(/export\s+default\s+([A-Za-z0-9_]+)\s*;?/);

      if (defaultFnMatch) {
        identifiedComponentName = defaultFnMatch[1];
        codeToTransform = codeToTransform.replace(/export\s+default\s+function\s+([A-Za-z0-9_]+)/, "function $1");
      } else if (defaultClassMatch) {
        identifiedComponentName = defaultClassMatch[1];
        codeToTransform = codeToTransform.replace(/export\s+default\s+class\s+([A-Za-z0-9_]+)/, "class $1");
      } else if (defaultVarMatch) {
        identifiedComponentName = defaultVarMatch[1];
        codeToTransform = codeToTransform.replace(/export\s+default\s+([A-Za-z0-9_]+)\s*;?/, "");
      } else if (/export\s+default\s+/.test(codeToTransform)) {
        codeToTransform = codeToTransform.replace(/export\s+default\s+/, "window.__RenderCandidate__ = ");
      }

      // Remove any remaining export keywords
      codeToTransform = codeToTransform.replace(/export\s+(?:default\s+)?(function|const|let|var|class)\s+/g, "$1 ");

      // If still no identified component name, look for any declared PascalCase identifier
      if (!identifiedComponentName) {
        const pascalMatches = Array.from(codeToTransform.matchAll(/(?:function|const|class)\s+([A-Z][A-Za-z0-9_]*)/g));
        if (pascalMatches.length > 0) {
          identifiedComponentName = pascalMatches[0][1];
        }
      }

      const iconDeclarations = Array.from(iconNames)
        .map((name) => `const ${name} = createMockIcon("${name}");`)
        .join("\n");

      return `
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <script src="https://cdn.tailwindcss.com"></script>
            <script src="https://unpkg.com/react@18/umd/react.development.js"></script>
            <script src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
            <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
            ${consoleHookScript}
            <style>
              body { background-color: #080a12; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
              ::-webkit-scrollbar { width: 6px; height: 6px; }
              ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); border-radius: 4px; }
            </style>
          </head>
          <body class="min-h-screen p-4">
            <div id="__runtime_error_box__" style="display: none; margin-bottom: 16px;"></div>
            <div id="root"></div>
            <script type="text/babel">
              const { useState, useEffect, useMemo, useRef, useCallback, useReducer, createContext, useContext } = React;

              function createMockIcon(iconName) {
                return function MockIcon(props) {
                  const size = props.size || 16;
                  const className = props.className || "w-4 h-4 inline-block";
                  return (
                    <svg
                      width={size}
                      height={size}
                      viewBox="0 0 24 24"
                      fill={props.fill || "none"}
                      stroke={props.stroke || "currentColor"}
                      strokeWidth={props.strokeWidth || 2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className={className}
                      style={props.style}
                    >
                      <circle cx="12" cy="12" r="9" opacity="0.25" />
                      <path d="M12 8v8M8 12h8" />
                    </svg>
                  );
                };
              }

              ${iconDeclarations}

              try {
                window.__RenderCandidate__ = null;

                ${codeToTransform}

                ${identifiedComponentName ? `if (typeof ${identifiedComponentName} !== "undefined") { window.__RenderCandidate__ = ${identifiedComponentName}; }` : ""}

                let ComponentToRender = window.__RenderCandidate__;
                if (!ComponentToRender) {
                  const candidates = [
                    typeof App !== "undefined" ? App : null,
                    typeof Dashboard !== "undefined" ? Dashboard : null,
                    typeof NeuralDashboard !== "undefined" ? NeuralDashboard : null,
                    typeof Component !== "undefined" ? Component : null,
                    typeof Preview !== "undefined" ? Preview : null,
                  ].filter(Boolean);
                  if (candidates.length > 0) {
                    ComponentToRender = candidates[0];
                  }
                }

                if (ComponentToRender) {
                  const root = ReactDOM.createRoot(document.getElementById("root"));
                  root.render(React.createElement(ComponentToRender));
                } else {
                  document.getElementById("root").innerHTML = '<div class="p-6 text-center text-neutral-400 text-sm">React component loaded. Ensure it exports a function or default component.</div>';
                }
              } catch (err) {
                console.error("Evaluation error:", err.message);
                const errBox = document.getElementById("__runtime_error_box__");
                if (errBox) {
                  errBox.style.display = "block";
                  errBox.innerHTML = '<div style="padding: 16px; background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.4); border-radius: 12px; color: #fca5a5; font-family: monospace; font-size: 12px;"><strong style="color: #ef4444;">Compilation Error:</strong><br/>' + err.message + '</div>';
                }
              }
            </script>
          </body>
        </html>
      `;
    }

    // 2. Mermaid Architecture Diagrams
    if (artifact.type === "mermaid") {
      return `
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
            ${consoleHookScript}
            <style>
              body { background-color: #080a12; color: #e2e8f0; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 24px; box-sizing: border-box; }
              .mermaid { width: 100%; display: flex; justify-content: center; }
            </style>
          </head>
          <body>
            <div id="__runtime_error_box__" style="display: none; position: fixed; top: 12px; left: 12px; right: 12px;"></div>
            <div class="mermaid">
              ${artifact.content}
            </div>
            <script>
              mermaid.initialize({ startOnLoad: true, theme: 'dark' });
            </script>
          </body>
        </html>
      `;
    }

    // 3. HTML Mockups
    if (artifact.type === "html") {
      const isFullDoc = /<!doctype html>|<html/i.test(artifact.content);
      if (isFullDoc) {
        if (artifact.content.includes("<head>")) {
          return artifact.content.replace("<head>", `<head>${consoleHookScript}`);
        } else if (artifact.content.includes("<head ")) {
          return artifact.content.replace(/<head[^>]*>/, `$&${consoleHookScript}`);
        }
        return `${consoleHookScript}${artifact.content}`;
      }

      // Inject tailwind automatically if not present
      const hasTailwind = artifact.content.includes("tailwindcss");
      const tailwindScript = hasTailwind ? "" : '<script src="https://cdn.tailwindcss.com"></script>';

      return `
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            ${tailwindScript}
            ${consoleHookScript}
            <style>
              body { background-color: #080a12; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
            </style>
          </head>
          <body class="p-4">
            <div id="__runtime_error_box__" style="display: none; margin-bottom: 16px;"></div>
            ${artifact.content}
          </body>
        </html>
      `;
    }

    // 4. Fallback (Markdown / Diff)
    return `
      <!DOCTYPE html>
      <html>
        <head>
          <meta charset="UTF-8" />
          <script src="https://cdn.tailwindcss.com"></script>
          <style>body { background: #080a12; color: #cbd5e1; font-family: monospace; padding: 16px; }</style>
        </head>
        <body>
          <pre style="white-space: pre-wrap; word-break: break-all;">${artifact.content}</pre>
        </body>
      </html>
    `;
  }, [artifact]);

  if (!artifact) {
    return (
      <div className={`flex flex-col items-center justify-center p-8 text-neutral-500 border border-dashed border-neutral-800 rounded-2xl ${className}`}>
        <Layers className="w-8 h-8 opacity-40 mb-2" />
        <p className="text-xs">No active artifact selected</p>
      </div>
    );
  }

  const getTypeBadgeTone = (type: Artifact["type"]) => {
    switch (type) {
      case "react":
        return "accent";
      case "html":
        return "ok";
      case "mermaid":
        return "info";
      default:
        return "default";
    }
  };

  const lineCount = artifact.content.split("\n").length;

  return (
    <div className={`flex flex-col h-full bg-[#0a0d18] border border-cyan-500/20 rounded-2xl overflow-hidden shadow-2xl ${className}`}>
      {/* ── Top Header Bar ── */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-neutral-900/80 border-b border-neutral-800 text-xs shrink-0">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="flex items-center gap-1.5 min-w-0">
            <FileCode className="w-4 h-4 text-cyan-400 shrink-0" />
            <span className="font-semibold text-white truncate max-w-[200px]" title={artifact.title}>
              {artifact.title}
            </span>
          </div>
          <Badge tone={getTypeBadgeTone(artifact.type)}>
            {artifact.type.toUpperCase()}
          </Badge>
          <span className="text-[10px] text-neutral-400 font-mono">
            v{artifact.version} · {lineCount} lines
          </span>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-1">
          <button
            onClick={handleCopy}
            className="p-1.5 rounded-lg hover:bg-neutral-800 text-neutral-400 hover:text-white transition"
            title="Copy source code"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>

          <button
            onClick={() => setShowPathInput(!showPathInput)}
            className="p-1.5 rounded-lg hover:bg-neutral-800 text-neutral-400 hover:text-white transition"
            title="Apply to Workspace"
          >
            <Download className="w-3.5 h-3.5 text-cyan-400" />
          </button>

          <button
            onClick={handlePopOut}
            className="p-1.5 rounded-lg hover:bg-neutral-800 text-neutral-400 hover:text-white transition"
            title="Open preview in new tab"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={() => setIframeKey((k) => k + 1)}
            className="p-1.5 rounded-lg hover:bg-neutral-800 text-neutral-400 hover:text-white transition"
            title="Reload preview"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>

          {onClose && (
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-neutral-800 text-neutral-400 hover:text-red-400 transition ml-1"
              title="Close Preview Pane"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* ── Mode Toggle Bar & Workspace Apply Form ── */}
      <div className="flex items-center justify-between px-4 py-1.5 bg-neutral-950/60 border-b border-neutral-800/80 text-xs shrink-0">
        <div className="flex items-center gap-1 bg-neutral-900/60 p-0.5 rounded-lg border border-neutral-800">
          <button
            onClick={() => setMode("preview")}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium transition ${
              mode === "preview" ? "bg-cyan-500/20 text-cyan-300 shadow-sm" : "text-neutral-400 hover:text-neutral-200"
            }`}
          >
            <Eye className="w-3 h-3" />
            Live Preview
          </button>
          <button
            onClick={() => setMode("code")}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium transition ${
              mode === "code" ? "bg-cyan-500/20 text-cyan-300 shadow-sm" : "text-neutral-400 hover:text-neutral-200"
            }`}
          >
            <Code className="w-3 h-3" />
            Source Code
          </button>
          <button
            onClick={() => setMode("console")}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium transition relative ${
              mode === "console" ? "bg-cyan-500/20 text-cyan-300 shadow-sm" : "text-neutral-400 hover:text-neutral-200"
            }`}
          >
            <Terminal className="w-3 h-3" />
            Console
            {consoleLogs.length > 0 && (
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 inline-block" />
            )}
          </button>
        </div>

        {applyResult && (
          <span className="text-[11px] text-emerald-400 font-mono animate-fade-in flex items-center gap-1">
            <Check className="w-3 h-3" /> {applyResult}
          </span>
        )}
      </div>

      {/* Workspace Apply Input Bar */}
      <AnimatePresence>
        {showPathInput && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="px-4 py-2 bg-neutral-900 border-b border-cyan-500/30 flex items-center gap-2 text-xs shrink-0 overflow-hidden"
          >
            <span className="text-neutral-400 font-mono text-[10px] shrink-0">Path:</span>
            <input
              type="text"
              value={customPath}
              onChange={(e) => setCustomPath(e.target.value)}
              placeholder="src/components/Dashboard.tsx"
              className="flex-1 bg-neutral-950 border border-neutral-700 rounded px-2 py-1 text-white text-xs font-mono outline-none focus:border-cyan-400"
            />
            <button
              onClick={handleApplyToWorkspace}
              disabled={applying}
              className="px-3 py-1 bg-cyan-600 hover:bg-cyan-500 text-white rounded font-medium text-[11px] transition flex items-center gap-1 shrink-0 cursor-pointer disabled:opacity-50"
            >
              {applying ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
              Apply to Project
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Main Pane Content ── */}
      <div className="flex-1 min-h-0 relative overflow-hidden bg-[#070913]">
        {/* MODE 1: Live Preview */}
        {mode === "preview" && (
          <iframe
            key={iframeKey}
            srcDoc={srcDocContent}
            sandbox="allow-scripts allow-modals"
            className="w-full h-full border-none bg-[#080a12]"
            title={artifact.title}
          />
        )}

        {/* MODE 2: Source Code */}
        {mode === "code" && (
          <div className="w-full h-full overflow-auto p-4 font-mono text-[12px] leading-relaxed text-neutral-300">
            <div className="flex gap-4">
              {/* Line Numbers */}
              <div className="select-none text-neutral-600 text-right shrink-0">
                {artifact.content.split("\n").map((_, i) => (
                  <div key={i}>{i + 1}</div>
                ))}
              </div>
              {/* Code Content */}
              <pre className="flex-1 overflow-x-auto text-emerald-300/90 whitespace-pre">
                {artifact.content}
              </pre>
            </div>
          </div>
        )}

        {/* MODE 3: Console Logs */}
        {mode === "console" && (
          <div className="w-full h-full flex flex-col p-3 text-xs font-mono">
            <div className="flex items-center justify-between pb-2 border-b border-neutral-800 text-neutral-400 text-[11px]">
              <span>Captured Console Output ({consoleLogs.length} events)</span>
              <button
                onClick={() => clearConsoleLogs(artifact.id)}
                className="hover:text-white transition"
              >
                Clear
              </button>
            </div>
            <div className="flex-1 overflow-auto space-y-1.5 pt-2">
              {consoleLogs.length === 0 ? (
                <div className="text-neutral-500 italic p-4 text-center">
                  No console logs captured from artifact.
                </div>
              ) : (
                consoleLogs.map((log, idx) => (
                  <div
                    key={idx}
                    className={`p-1.5 rounded flex items-start gap-2 ${
                      log.type === "error"
                        ? "bg-red-950/40 text-red-300 border border-red-900/40"
                        : log.type === "warn"
                        ? "bg-amber-950/40 text-amber-300 border border-amber-900/40"
                        : "text-neutral-300 bg-neutral-900/40"
                    }`}
                  >
                    <span className="text-[10px] text-neutral-500 shrink-0">{log.timestamp}</span>
                    <span className="uppercase text-[9px] font-bold shrink-0 opacity-75">{log.type}</span>
                    <span className="flex-1 break-all whitespace-pre-wrap">{log.message}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
