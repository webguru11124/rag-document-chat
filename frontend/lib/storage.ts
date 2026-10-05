"use client";

import { useEffect, useRef, useState } from "react";

/**
 * useState that survives reloads via localStorage. The stored value is read after
 * mount so server and client render the same markup first. Storage can be missing
 * or full (private windows, quotas), so every access is guarded.
 */
export function usePersistentState<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(initial);
  const [loaded, setLoaded] = useState(false);
  const initialRef = useRef(initial);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(key);
      if (raw !== null) {
        const stored = JSON.parse(raw);
        const base = initialRef.current;
        const isPlainObject = (v: unknown) => typeof v === "object" && v !== null && !Array.isArray(v);
        // Merge objects so fields added in later versions get their defaults.
        setValue(isPlainObject(base) && isPlainObject(stored) ? { ...base, ...stored } : stored);
      }
    } catch {
      // ignore unreadable storage
    }
    setLoaded(true);
  }, [key]);

  // Debounced, so a streaming answer isn't serialised on every token.
  useEffect(() => {
    if (!loaded) return;
    const timer = window.setTimeout(() => {
      try {
        window.localStorage.setItem(key, JSON.stringify(value));
      } catch {
        // ignore quota or privacy-mode errors
      }
    }, 300);
    return () => window.clearTimeout(timer);
  }, [key, value, loaded]);

  return [value, setValue, loaded] as const;
}
