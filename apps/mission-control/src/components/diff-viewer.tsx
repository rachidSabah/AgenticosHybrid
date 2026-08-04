"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import type { WorktreeDiffFile } from "@/lib/types";
import { DiffEditor } from "@monaco-editor/react";
import {
  FilePlus, FileEdit, FileMinus, GitMerge, RefreshCw,
  Check, X, ChevronRight, AlertTriangle, Loader2,
} from "lucide-react";

export function DiffViewer({
  branchName,
  onClose,
}: {
  branchName: string;
  onClose: () => void;
}) {
  const [diffFiles, setDiffFiles] = useState<WorktreeDiffFile[]>([]);
  const [selectedFile, setSelectedFile] = useState<WorktreeDiffFile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [merging, setMerging] = useState(false);
  const [mergeResult, setMergeResult] = useState<string | null>(null);
  const [originalContent, setOriginalContent] = useState<string>("");

  const loadDiff = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const files = await api.worktreeDiff(branchName);
      setDiffFiles(files ?? []);
      if (files && files.length > 0) {
        setSelectedFile(files[0]);
        // Try to load original content
        try {
          const res = await api.worktreeFile(branchName, files[0].file);
          setOriginalContent(res?.content ?? "");
        } catch {
          setOriginalContent("");
        }
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [branchName]);

  useEffect(() => {
    void loadDiff();
  }, [loadDiff]);

  const handleSelectFile = async (file: WorktreeDiffFile) => {
    setSelectedFile(file);
    try {
      const res = await api.worktreeFile(branchName, file.file);
      setOriginalContent(res?.content ?? "");
    } catch {
      setOriginalContent("");
    }
  };

  const handleMerge = async () => {
    setMerging(true);
    setMergeResult(null);
    try {
      const result = await api.worktreeMerge(branchName);
      if (result.merged) {
        setMergeResult(`✓ ${result.message ?? "Merged successfully"}`);
      } else {
        setMergeResult(`✗ ${result.error ?? "Merge failed — conflicts detected"}`);
      }
    } catch (err) {
      setMergeResult(`✗ Merge failed: ${String(err)}`);
    } finally {
      setMerging(false);
    }
  };

  const statusIcon = (status: string) => {
    switch (status) {
      case "added": return <FilePlus size={12} className="text-emerald-400" />;
      case "modified": return <FileEdit size={12} className="text-amber-400" />;
      case "deleted": return <FileMinus size={12} className="text-red-400" />;
      default: return <FileEdit size={12} className="text-white/40" />;
    }
  };

  return (
    <div className="flex h-full flex-col bg-[#0a0b10] text-[#e2e8f0]">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <GitMerge size={14} className="text-amber-400" />
          <span className="text-xs font-semibold">Review Changes — {branchName}</span>
          <span className="text-[10px] text-white/40">{diffFiles.length} files changed</span>
        </div>
        <div className="flex items-center gap-2">
          {mergeResult && (
            <span className={`text-[10px] ${mergeResult.startsWith("✓") ? "text-emerald-400" : "text-red-400"}`}>
              {mergeResult}
            </span>
          )}
          <button onClick={() => void loadDiff()} className="rounded-md border border-white/10 px-2 py-1 text-[10px] text-white/60 hover:bg-white/10">
            <RefreshCw size={11} />
          </button>
          <button
            onClick={handleMerge}
            disabled={merging || diffFiles.length === 0}
            className="rounded-md bg-emerald-500/20 px-3 py-1 text-[10px] font-medium text-emerald-300 hover:bg-emerald-500/30 disabled:opacity-50"
          >
            {merging ? <Loader2 size={11} className="animate-spin" /> : "Merge to main"}
          </button>
          <button onClick={onClose} className="rounded-md p-1 text-white/40 hover:bg-white/10">
            <X size={14} />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex flex-1 items-center justify-center">
          <Loader2 size={20} className="animate-spin text-white/30" />
        </div>
      ) : error ? (
        <div className="flex flex-1 items-center justify-center text-xs text-red-400">{error}</div>
      ) : diffFiles.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-1 text-white/30">
          <Check size={24} />
          <span className="text-xs">No changes — worktree is clean</span>
        </div>
      ) : (
        <div className="flex flex-1 overflow-hidden">
          {/* File tree sidebar */}
          <div className="w-56 border-r border-white/10 overflow-y-auto">
            {diffFiles.map((file) => (
              <button
                key={file.file}
                onClick={() => handleSelectFile(file)}
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] transition ${
                  selectedFile?.file === file.file ? "bg-amber-500/10 text-amber-300" : "text-white/60 hover:bg-white/5"
                }`}
              >
                {statusIcon(file.status)}
                <span className="truncate flex-1">{file.file.split("/").pop()}</span>
                <span className="text-[9px] text-emerald-400/60">+{file.additions}</span>
                <span className="text-[9px] text-red-400/60">-{file.deletions}</span>
              </button>
            ))}
          </div>

          {/* Diff view */}
          <div className="flex-1 overflow-hidden">
            {selectedFile ? (
              <div className="flex h-full flex-col">
                <div className="flex items-center gap-2 border-b border-white/10 px-3 py-1.5">
                  {statusIcon(selectedFile.status)}
                  <span className="font-mono text-[10px] text-white/60">{selectedFile.file}</span>
                  <span className="ml-auto text-[9px] text-emerald-400/60">+{selectedFile.additions}</span>
                  <span className="text-[9px] text-red-400/60">-{selectedFile.deletions}</span>
                </div>
                <div className="flex-1 overflow-hidden">
                  <DiffEditor
                    original={originalContent}
                    modified={selectedFile.diff}
                    language="plaintext"
                    theme="vs-dark"
                    options={{
                      readOnly: true,
                      renderSideBySide: true,
                      minimap: { enabled: false },
                      fontSize: 11,
                      lineNumbers: "on",
                    }}
                  />
                </div>
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-white/30 text-xs">
                Select a file to view diff
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
