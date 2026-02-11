"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useTheme } from "@/hooks/useTheme";
import { toast } from "sonner";
import api from "@/lib/api";

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [gmailConnected, setGmailConnected] = useState(false);
  const [gmailLoading, setGmailLoading] = useState(true);
  const [exchanging, setExchanging] = useState(false);

  useEffect(() => {
    async function load() {
      const supabase = createClient();
      const {
        data: { user },
      } = await supabase.auth.getUser();
      if (user) {
        setEmail(user.email || "");
      }
      setLoading(false);
    }
    load();
  }, []);

  // On mount: check for Google OAuth code in URL (redirect from Google)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const state = params.get("state");

    if (code && state) {
      // Clean URL immediately
      window.history.replaceState({}, "", "/settings");

      setExchanging(true);
      api
        .post("/users/exchange-gmail-code", {
          code,
          state,
          redirect_uri: `${window.location.origin}/settings`,
        })
        .then(({ data }) => {
          if (data.connected) {
            setGmailConnected(true);
            toast.success("Gmail connected successfully");
          }
        })
        .catch((err) => {
          const detail = err.response?.data?.detail || "Failed to connect Gmail";
          toast.error(detail);
        })
        .finally(() => {
          setExchanging(false);
          setGmailLoading(false);
        });
    } else {
      // No code — just check status
      api
        .get("/users/gmail-status")
        .then(({ data }) => setGmailConnected(data.connected))
        .catch(() => {})
        .finally(() => setGmailLoading(false));
    }
  }, []);

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    window.location.href = "/login";
  }

  async function handleConnectGmail() {
    try {
      const { data } = await api.post("/users/gmail-auth-url", {
        redirect_uri: `${window.location.origin}/settings`,
      });
      // Navigate to Google consent screen
      window.location.href = data.url;
    } catch (err: any) {
      const detail = err.response?.data?.detail || "Failed to start Gmail connection";
      toast.error(detail);
    }
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

      {/* Email Sending */}
      <section className="space-y-4">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Email Sending
        </h2>
        <div className="border border-border rounded-lg">
          <div className="flex items-center justify-between px-4 py-3">
            <div>
              <p className="text-sm font-medium">Gmail</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {gmailLoading || exchanging ? (
                  <span>
                    {exchanging ? "Connecting Gmail..." : (
                      <span className="inline-block w-48 h-4 bg-muted animate-pulse rounded" />
                    )}
                  </span>
                ) : gmailConnected ? (
                  "Connected — emails will send from your Gmail"
                ) : (
                  "Not connected — connect to send emails from your account"
                )}
              </p>
            </div>
            {!gmailLoading && !exchanging && (
              <button
                onClick={handleConnectGmail}
                className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
                  gmailConnected
                    ? "text-muted-foreground border border-border hover:bg-muted"
                    : "text-foreground bg-primary/10 border border-primary/30 hover:bg-primary/20"
                }`}
              >
                {gmailConnected ? "Reconnect" : "Connect Gmail"}
              </button>
            )}
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
            { keys: "\u2318 K", desc: "Open command palette" },
            { keys: "\u2318 N", desc: "New application" },
            { keys: "\u2318 G", desc: "Go to Generate" },
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
