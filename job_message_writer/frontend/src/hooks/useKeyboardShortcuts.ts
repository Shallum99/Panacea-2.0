"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function useKeyboardShortcuts() {
  const router = useRouter();

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      // Skip if user is typing in an input/textarea
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if ((e.target as HTMLElement)?.isContentEditable) return;

      // Cmd/Ctrl shortcuts
      if (e.metaKey || e.ctrlKey) {
        switch (e.key) {
          case "n":
            e.preventDefault();
            router.push("/generate");
            break;
          case "g":
            e.preventDefault();
            router.push("/generate");
            break;
          case "j":
            e.preventDefault();
            document.dispatchEvent(new CustomEvent("toggle-chat"));
            break;
        }
        return;
      }

      // Plain key shortcuts (no modifier, not in input)
      switch (e.key) {
        case "g":
          if (e.shiftKey) {
            e.preventDefault();
            router.push("/generate");
          }
          break;
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [router]);
}
