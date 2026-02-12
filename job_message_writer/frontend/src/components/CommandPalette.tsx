"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";

const pages = [
  { name: "Dashboard", href: "/dashboard", shortcut: "H", group: "Pages" },
  { name: "Resumes", href: "/resumes", shortcut: "R", group: "Pages" },
  { name: "Generate Message", href: "/generate", shortcut: "G", group: "Pages" },
  { name: "Tailor Resume", href: "/tailor", shortcut: "T", group: "Pages" },
  { name: "Agentic Apply", href: "/agentic-apply", shortcut: "A", group: "Pages" },
  { name: "Settings", href: "/settings", shortcut: "S", group: "Pages" },
];

const actions = [
  { name: "New Application", href: "/generate", shortcut: "N", group: "Actions" },
  { name: "Upload Resume", href: "/resumes", shortcut: "U", group: "Actions" },
  { name: "Open Chat", href: "__chat__", shortcut: "J", group: "Actions" },
];

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const router = useRouter();

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  function navigate(href: string) {
    setOpen(false);
    if (href === "__chat__") {
      document.dispatchEvent(new CustomEvent("toggle-chat"));
      return;
    }
    router.push(href);
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={() => setOpen(false)}
      />

      {/* Palette */}
      <div className="absolute top-[20%] left-1/2 -translate-x-1/2 w-full max-w-lg">
        <Command
          className="bg-[#18181b] border border-border rounded-xl shadow-2xl overflow-hidden"
          loop
        >
          <Command.Input
            placeholder="Type a command or search..."
            className="w-full px-4 py-3 text-sm bg-transparent border-b border-border outline-none placeholder:text-muted-foreground"
          />
          <Command.List className="max-h-72 overflow-y-auto p-2">
            <Command.Empty className="px-4 py-8 text-center text-sm text-muted-foreground">
              No results found.
            </Command.Empty>

            <Command.Group
              heading="Pages"
              className="text-xs text-muted-foreground px-2 py-1.5"
            >
              {pages.map((item) => (
                <Command.Item
                  key={item.href}
                  value={item.name}
                  onSelect={() => navigate(item.href)}
                  className="flex items-center justify-between px-3 py-2 text-sm rounded-md cursor-pointer data-[selected=true]:bg-muted transition-colors"
                >
                  <span>{item.name}</span>
                  <kbd className="text-xs text-muted-foreground font-mono bg-muted/50 px-1.5 py-0.5 rounded">
                    {item.shortcut}
                  </kbd>
                </Command.Item>
              ))}
            </Command.Group>

            <Command.Group
              heading="Actions"
              className="text-xs text-muted-foreground px-2 py-1.5 mt-2"
            >
              {actions.map((item) => (
                <Command.Item
                  key={item.name}
                  value={item.name}
                  onSelect={() => navigate(item.href)}
                  className="flex items-center justify-between px-3 py-2 text-sm rounded-md cursor-pointer data-[selected=true]:bg-muted transition-colors"
                >
                  <span>{item.name}</span>
                  <kbd className="text-xs text-muted-foreground font-mono bg-muted/50 px-1.5 py-0.5 rounded">
                    {item.shortcut}
                  </kbd>
                </Command.Item>
              ))}
            </Command.Group>
          </Command.List>

          <div className="border-t border-border px-4 py-2 flex items-center justify-between text-xs text-muted-foreground">
            <span>Navigate with arrow keys</span>
            <div className="flex gap-2">
              <kbd className="font-mono bg-muted/50 px-1.5 py-0.5 rounded">Enter</kbd>
              <span>to select</span>
              <kbd className="font-mono bg-muted/50 px-1.5 py-0.5 rounded">Esc</kbd>
              <span>to close</span>
            </div>
          </div>
        </Command>
      </div>
    </div>
  );
}
