/**
 * Safety utilities for rendering API data without crashing.
 *
 * Every function returns a safe default when the input is undefined/null/NaN.
 * Use these in React components to prevent "Cannot read properties of
 * undefined" crashes when the backend returns incomplete data or is offline.
 */

/** Returns a safe number (0 if undefined/null/NaN). */
export function safeNum(value: unknown, defaultValue = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : defaultValue;
}

/** Returns a safe integer (0 if undefined/null/NaN). */
export function safeInt(value: unknown, defaultValue = 0): number {
  return Math.trunc(safeNum(value, defaultValue));
}

/** Returns a safe string ("" if undefined/null). */
export function safeStr(value: unknown, defaultValue = ""): string {
  if (value === undefined || value === null) return defaultValue;
  return String(value);
}

/** Returns a safe array ([] if undefined/null/not-array). */
export function safeArr<T>(value: unknown, defaultValue: T[] = []): T[] {
  return Array.isArray(value) ? value : defaultValue;
}

/** Returns a safe object ({} if undefined/null/not-object). */
export function safeObj<T extends Record<string, unknown>>(value: unknown, defaultValue: T = {} as T): T {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as T;
  }
  return defaultValue;
}

/** Safely call .toFixed() on any value. Returns "0" for undefined/null/NaN. */
export function safeFixed(value: unknown, digits = 0, fallback = "0"): string {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : fallback;
}

/** Safely get .length of any value. Returns 0 for undefined/null/non-array. */
export function safeLen(value: unknown): number {
  if (Array.isArray(value)) return value.length;
  if (typeof value === "string") return value.length;
  return 0;
}

/** Safely format a percentage. Returns "0%" for undefined/null/NaN. */
export function safePercent(value: unknown, digits = 0): string {
  return `${safeFixed(value, digits)}%`;
}

/** Safely format milliseconds. Returns "0ms" for undefined/null/NaN. */
export function safeMs(value: unknown, digits = 0): string {
  return `${safeFixed(value, digits)}ms`;
}

/** Safely format bytes to MB. */
export function safeMb(value: unknown, digits = 1): string {
  const n = safeNum(value);
  return n > 0 ? `${(n / 1024 / 1024).toFixed(digits)} MB` : "0 MB";
}

/** Safely format bytes to GB. */
export function safeGb(value: unknown, digits = 1): string {
  const n = safeNum(value);
  return n > 0 ? `${(n / 1024 / 1024 / 1024).toFixed(digits)} GB` : "0 GB";
}

/** Safely access a nested property. Returns undefined if any part is missing. */
export function safeGet(obj: unknown, ...path: (string | number)[]): unknown {
  let current: unknown = obj;
  for (const key of path) {
    if (current === undefined || current === null) return undefined;
    current = (current as Record<string | number, unknown>)[key];
  }
  return current;
}

/** Safely call .map() on any value. Returns [] for undefined/null. */
export function safeMap<T, R>(value: unknown, fn: (item: T, index: number) => R): R[] {
  return safeArr<T>(value).map(fn);
}

/** Safely call .filter() on any value. Returns [] for undefined/null. */
export function safeFilter<T>(value: unknown, fn: (item: T, index: number) => boolean): T[] {
  return safeArr<T>(value).filter(fn);
}

/** Safely call Object.keys() on any value. Returns [] for undefined/null. */
export function safeKeys(value: unknown): string[] {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.keys(value);
  }
  return [];
}

/** Safely call Object.values() on any value. Returns [] for undefined/null. */
export function safeValues<T>(value: unknown): T[] {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.values(value) as T[];
  }
  return [];
}

/** Safely call Object.entries() on any value. Returns [] for undefined/null. */
export function safeEntries<T>(value: unknown): [string, T][] {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.entries(value) as [string, T][];
  }
  return [];
}
