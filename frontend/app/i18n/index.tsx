"use client";
import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import zh from "./zh";
import en from "./en";

type Locale = "zh" | "en";
type Translations = Record<string, string>;

const translations: Record<Locale, Translations> = { zh, en };

function detectLocale(): Locale {
  if (typeof window === "undefined") return "zh";
  const saved = localStorage.getItem("ses_locale");
  if (saved === "en" || saved === "zh") return saved;
  const nav = navigator.language || "";
  if (nav.startsWith("en")) return "en";
  return "zh";
}

interface LocaleContextType {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string, params?: Record<string, string | number>) => string;
}

const LocaleContext = createContext<LocaleContextType>({
  locale: "zh",
  setLocale: () => {},
  t: (key) => key,
});

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("zh");

  useEffect(() => {
    setLocaleState(detectLocale());
  }, []);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    localStorage.setItem("ses_locale", l);
  }, []);

  const t = useCallback((key: string, params?: Record<string, string | number>): string => {
    const str = translations[locale]?.[key] || translations["zh"]?.[key] || key;
    if (!params) return str;
    return str.replace(/\{(\w+)\}/g, (_, k) => String(params[k] ?? ""));
  }, [locale]);

  return <LocaleContext.Provider value={{ locale, setLocale, t }}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  return useContext(LocaleContext);
}

export function useT() {
  const { t } = useContext(LocaleContext);
  return t;
}
