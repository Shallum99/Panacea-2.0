"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import CommandPalette from "@/components/CommandPalette";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import { useTheme } from "@/hooks/useTheme";
import ChatPanel from "@/components/chat/ChatPanel";
import {
  LayoutDashboard,
  Search,
  UserCircle,
  FileText,
  Sparkles,
  Send,
  CreditCard,
  Settings,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Sun,
  Moon,
  Command,
  MessageSquare,
  Wand2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

const nav: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/jobs", label: "Jobs", icon: Search },
  { href: "/profile", label: "Profile", icon: UserCircle },
  { href: "/resumes", label: "Resumes", icon: FileText },
  { href: "/generate", label: "Generate", icon: Sparkles },
  { href: "/agentic-apply", label: "Apply", icon: Wand2 },
  { href: "/applications", label: "Applications", icon: Send },
  { href: "/pricing", label: "Pricing", icon: CreditCard },
];

const STORAGE_KEY = "sidebar-collapsed";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const supabase = createClient();
  const { theme, toggle } = useTheme();
  const [collapsed, setCollapsed] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  useKeyboardShortcuts();

  // Listen for toggle-chat custom event (from Cmd+J shortcut)
  useEffect(() => {
    function handleToggle() {
      setChatOpen((prev) => !prev);
    }
    document.addEventListener("toggle-chat", handleToggle);
    return () => document.removeEventListener("toggle-chat", handleToggle);
  }, []);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "true") setCollapsed(true);
    setMounted(true);
  }, []);

  function toggleCollapsed() {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem(STORAGE_KEY, String(next));
  }

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.push("/login");
  }

  function openCommandPalette() {
    document.dispatchEvent(
      new KeyboardEvent("keydown", { key: "k", metaKey: true })
    );
  }

  function isActive(href: string) {
    return pathname === href || pathname.startsWith(href + "/");
  }

  const w = !mounted ? "w-56" : collapsed ? "w-[60px]" : "w-56";

  return (
    <div className="flex h-screen">
      <CommandPalette />

      <aside
        className={`${w} bg-sidebar flex flex-col shrink-0 transition-all duration-200 overflow-hidden border-r border-border`}
      >
        {/* Brand */}
        <div className={`flex items-center min-h-[56px] ${collapsed ? "justify-center px-2" : "justify-between px-4"}`}>
          <Link href="/dashboard" className="text-gradient text-lg font-semibold tracking-tight whitespace-nowrap">
            {collapsed ? "P" : "Panacea"}
          </Link>
          {!collapsed && (
            <button
              onClick={toggle}
              className="w-7 h-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground transition-colors"
            >
              {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
            </button>
          )}
        </div>

        {/* Nav */}
        <nav className={`flex-1 py-2 space-y-0.5 ${collapsed ? "px-1.5" : "px-2"}`}>
          {nav.map((item) => {
            const active = isActive(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                title={collapsed ? item.label : undefined}
                className={`flex items-center gap-3 py-2 rounded-lg text-[13px] transition-colors ${
                  collapsed ? "justify-center px-0" : "px-3"
                } ${
                  active
                    ? "bg-foreground/[0.08] text-foreground font-medium"
                    : "text-muted-foreground hover:text-foreground hover:bg-foreground/[0.04]"
                }`}
              >
                <Icon size={17} className="shrink-0" />
                {!collapsed && <span className="whitespace-nowrap">{item.label}</span>}
              </Link>
            );
          })}
        </nav>

        {/* Bottom */}
        <div className={`py-2 space-y-0.5 border-t border-border ${collapsed ? "px-1.5" : "px-2"}`}>
          <button
            onClick={() => setChatOpen(true)}
            title={collapsed ? "Chat (Cmd+J)" : undefined}
            className={`w-full flex items-center py-2 text-[13px] text-muted-foreground hover:text-foreground hover:bg-foreground/[0.04] rounded-lg transition-colors ${
              collapsed ? "justify-center px-0" : "justify-between px-3"
            }`}
          >
            {collapsed ? (
              <MessageSquare size={17} />
            ) : (
              <>
                <span className="flex items-center gap-3">
                  <MessageSquare size={17} />
                  <span>Chat</span>
                </span>
                <kbd className="text-[10px] font-mono text-muted-foreground/60 bg-foreground/[0.05] px-1.5 py-0.5 rounded">
                  {typeof navigator !== "undefined" && /Mac/.test(navigator.userAgent) ? "\u2318J" : "Ctrl J"}
                </kbd>
              </>
            )}
          </button>

          <button
            onClick={openCommandPalette}
            title={collapsed ? "Search (Cmd+K)" : undefined}
            className={`w-full flex items-center py-2 text-[13px] text-muted-foreground hover:text-foreground hover:bg-foreground/[0.04] rounded-lg transition-colors ${
              collapsed ? "justify-center px-0" : "justify-between px-3"
            }`}
          >
            {collapsed ? (
              <Command size={17} />
            ) : (
              <>
                <span className="flex items-center gap-3">
                  <Command size={17} />
                  <span>Search</span>
                </span>
                <kbd className="text-[10px] font-mono text-muted-foreground/60 bg-foreground/[0.05] px-1.5 py-0.5 rounded">
                  {typeof navigator !== "undefined" && /Mac/.test(navigator.userAgent) ? "\u2318K" : "Ctrl K"}
                </kbd>
              </>
            )}
          </button>

          {(() => {
            const active = isActive("/settings");
            return (
              <Link
                href="/settings"
                title={collapsed ? "Settings" : undefined}
                className={`flex items-center gap-3 py-2 text-[13px] rounded-lg transition-colors ${
                  collapsed ? "justify-center px-0" : "px-3"
                } ${
                  active
                    ? "bg-foreground/[0.08] text-foreground font-medium"
                    : "text-muted-foreground hover:text-foreground hover:bg-foreground/[0.04]"
                }`}
              >
                <Settings size={17} className="shrink-0" />
                {!collapsed && <span>Settings</span>}
              </Link>
            );
          })()}

          <button
            onClick={handleSignOut}
            title={collapsed ? "Sign Out" : undefined}
            className={`w-full flex items-center gap-3 py-2 text-[13px] text-muted-foreground hover:text-destructive hover:bg-foreground/[0.04] rounded-lg transition-colors ${
              collapsed ? "justify-center px-0" : "px-3"
            }`}
          >
            <LogOut size={17} className="shrink-0" />
            {!collapsed && <span>Sign Out</span>}
          </button>

          <button
            onClick={toggleCollapsed}
            className={`w-full flex items-center py-2 text-[13px] text-muted-foreground hover:text-foreground hover:bg-foreground/[0.04] rounded-lg transition-colors ${
              collapsed ? "justify-center px-0" : "px-3 gap-3"
            }`}
          >
            {collapsed ? (
              <PanelLeftOpen size={17} />
            ) : (
              <>
                <PanelLeftClose size={17} />
                <span>Collapse</span>
              </>
            )}
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto bg-background">
        <div className="p-6 lg:p-8 max-w-screen-2xl mx-auto">{children}</div>
      </main>

      <ChatPanel open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  );
}
