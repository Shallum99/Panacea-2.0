"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useTheme } from "@/hooks/useTheme";
import { toast } from "sonner";

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const supabase = createClient();
      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        setEmail(user.email || "");
      }
      setLoading(false);
    }
    load();
  }, []);

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    window.location.href = "/login";
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Manage your account and preferences
        </p>
      </div>

      {/* Account */}
      <section className="space-y-4">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Account
        </h2>
        <div className="border border-border rounded-lg divide-y divide-border">
          <div className="flex items-center justify-between px-4 py-3">
            <div>
              <p className="text-sm font-medium">Email</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {loading ? (
                  <span className="inline-block w-40 h-4 bg-muted animate-pulse rounded" />
                ) : (
                  email
                )}
              </p>
            </div>
          </div>
          <div className="flex items-center justify-between px-4 py-3">
            <div>
              <p className="text-sm font-medium">Sign out</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                End your current session
              </p>
            </div>
            <button
              onClick={handleSignOut}
              className="px-3 py-1.5 text-xs text-destructive border border-destructive/30 rounded-md hover:bg-destructive/10 transition-colors"
            >
              Sign Out
            </button>
          </div>
        </div>
      </section>

      {/* Appearance */}
      <section className="space-y-4">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Appearance
        </h2>
        <div className="border border-border rounded-lg">
          <div className="flex items-center justify-between px-4 py-3">
            <div>
              <p className="text-sm font-medium">Theme</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Choose your preferred color scheme
              </p>
            </div>
            <div className="flex gap-1 bg-muted rounded-lg p-0.5">
              <button
                onClick={() => {
                  setTheme("dark");
                  toast.success("Switched to dark mode");
                }}
                className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
                  theme === "dark"
                    ? "bg-background text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Dark
              </button>
              <button
                onClick={() => {
                  setTheme("light");
                  toast.success("Switched to light mode");
                }}
                className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
                  theme === "light"
                    ? "bg-background text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Light
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Keyboard Shortcuts */}
      <section className="space-y-4">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Keyboard Shortcuts
        </h2>
        <div className="border border-border rounded-lg divide-y divide-border">
          {[
            { keys: "⌘ K", desc: "Open command palette" },
            { keys: "⌘ N", desc: "New application" },
            { keys: "⌘ G", desc: "Go to Generate" },
          ].map((shortcut) => (
            <div
              key={shortcut.keys}
              className="flex items-center justify-between px-4 py-2.5"
            >
              <p className="text-sm text-muted-foreground">{shortcut.desc}</p>
              <kbd className="text-xs font-mono bg-muted/50 px-2 py-1 rounded">
                {shortcut.keys}
              </kbd>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
