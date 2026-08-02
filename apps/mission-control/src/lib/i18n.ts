// Minimal i18n helper — no external dependency for simplicity.
// Replace with next-intl when full localization is needed.

import messages from "../../messages/en.json";

type Messages = typeof messages;

const locales = ["en"] as const;
type Locale = (typeof locales)[number];

let currentLocale: Locale = "en";

export function setLocale(locale: Locale) {
  currentLocale = locale;
}

export function getLocale(): Locale {
  return currentLocale;
}

export function t(path: string): string {
  const keys = path.split(".");
  let value: unknown = messages;
  for (const key of keys) {
    if (typeof value !== "object" || value === null) return path;
    value = (value as Record<string, unknown>)[key];
  }
  return typeof value === "string" ? value : path;
}

export type { Locale };
export { locales };
