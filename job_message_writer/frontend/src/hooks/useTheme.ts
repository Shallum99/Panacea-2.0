"use client";

import { useEffect, useState } from "react";

type Theme = "dark" | "light";

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>("dark");

  useEffect(() => {
    const stored = localStorage.getItem("theme") as Theme | null;
    if (stored) {
      setThemeState(stored);
      applyTheme(stored);
    }
  }, []);

  function setTheme(t: Theme) {
    setThemeState(t);
    localStorage.setItem("theme", t);
    applyTheme(t);
  }

  function toggle() {
    setTheme(theme === "dark" ? "light" : "dark");
  }

  return { theme, setTheme, toggle };
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;

  if (theme === "light") {
    root.classList.remove("dark");
    root.classList.add("light");
    root.style.setProperty("--background", "#fafafa");
    root.style.setProperty("--foreground", "#09090b");
    root.style.setProperty("--muted", "#f4f4f5");
    root.style.setProperty("--muted-foreground", "#71717a");
    root.style.setProperty("--border", "#e4e4e7");
    root.style.setProperty("--accent", "#2563eb");
    root.style.setProperty("--accent-foreground", "#ffffff");
  } else {
    root.classList.remove("light");
    root.classList.add("dark");
    root.style.setProperty("--background", "#09090b");
    root.style.setProperty("--foreground", "#fafafa");
    root.style.setProperty("--muted", "#27272a");
    root.style.setProperty("--muted-foreground", "#a1a1aa");
    root.style.setProperty("--border", "#27272a");
    root.style.setProperty("--accent", "#3b82f6");
    root.style.setProperty("--accent-foreground", "#ffffff");
  }
}
