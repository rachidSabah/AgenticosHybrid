"use client";

import { useEffect, useRef } from "react";
import * as monaco from "monaco-editor";
import { useTheme } from "@/components/theme-provider";

interface Props {
  value: string;
  language?: string;
  readOnly?: boolean;
  onChange?: (value: string) => void;
  className?: string;
}

export function MonacoEditor({ value, language = "json", readOnly = false, onChange, className = "" }: Props) {
  const editorRef = useRef<HTMLDivElement>(null);
  const editorInstanceRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const isUpdatingRef = useRef(false);
  const onChangeRef = useRef(onChange);
  const valueRef = useRef(value);
  const { theme } = useTheme();

  // Keep refs in sync without triggering re-renders
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    valueRef.current = value;
  }, [value]);

  useEffect(() => {
    if (!editorRef.current || editorInstanceRef.current) return;

    // Ensure monaco is loaded
    if (typeof monaco === "undefined") return;

    const editor = monaco.editor.create(editorRef.current, {
      value: valueRef.current,
      language,
      readOnly,
      theme: theme === "dark" ? "vs-dark" : "vs",
      automaticLayout: true,
      minimap: { enabled: false },
      fontSize: 12,
      lineNumbers: "on",
      renderLineHighlight: "line",
      scrollBeyondLastLine: false,
      tabSize: 2,
      wordWrap: "on",
      formatOnPaste: true,
      formatOnType: true,
    });

    editorInstanceRef.current = editor;

    editor.onDidChangeModelContent(() => {
      if (!isUpdatingRef.current && onChangeRef.current) {
        onChangeRef.current(editor.getValue());
      }
    });

    // Cleanup on unmount
    return () => {
      editor.dispose();
      editorInstanceRef.current = null;
    };
  }, [language, readOnly]);

  // Update editor value when prop changes (but not when we're typing)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const editor = editorInstanceRef.current;
    if (editor && editor.getValue() !== valueRef.current) {
      isUpdatingRef.current = true;
      editor.setValue(valueRef.current);
      isUpdatingRef.current = false;
    }
  }, [value]);

  // Sync Monaco theme when user theme changes
  useEffect(() => {
    monaco.editor.setTheme(theme === "dark" ? "vs-dark" : "vs");
  }, [theme]);

  return <div ref={editorRef} className={`h-full w-full ${className}`} />;
}