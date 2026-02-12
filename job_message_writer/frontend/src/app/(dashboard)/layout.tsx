"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import CommandPalette from "@/components/CommandPalette";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import { useTheme } from "@/hooks/useTheme";
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
  ChevronLeft,
  ChevronRight,
  Sun,
  Moon,
  Command,
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

  useKeyboardShortcuts();

  // Hydrate collapsed state from localStorage
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "true") {
      setCollapsed(true);
    }
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

  // Prevent flash of wrong sidebar width before hydration
  const sidebarWidth = !mounted ? "w-56" : collapsed ? "w-16" : "w-56";

  return (
    <div className="flex h-screen">
      <CommandPalette />

      {/* Sidebar */}
      <aside
        className={`${sidebarWidth} border-r border-border flex flex-col shrink-0 transition-all duration-200 overflow-hidden`}
      >
        {/* Brand + Theme toggle */}
        <div className="p-4 border-b border-border flex items-center justify-between min-h-[57px]">
          <Link
            href="/dashboard"
            className="text-lg font-bold tracking-tight text-gradient whitespace-nowrap"
          >
            {collapsed ? "P" : "Panacea"}
          </Link>
          {!collapsed && (
            <button
              onClick={toggle}
              className="w-7 h-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
              title={
                theme === "dark"
                  ? "Switch to light mode"
                  : "Switch to dark mode"
              }
            >
              {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
            </button>
          )}
        </div>

        {/* Main navigation */}
        <nav className="flex-1 p-2 space-y-0.5">
          {nav.map((item) => {
            const active = isActive(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                title={collapsed ? item.label : undefined}
                className={`flex items-center gap-3 py-2 text-sm rounded-md transition-colors relative ${
                  collapsed ? "justify-center px-0" : "px-3"
                } ${
                  active
                    ? "bg-accent/10 text-foreground border-l-[3px] border-accent"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50 border-l-[3px] border-transparent"
                }`}
              >
                <Icon
                  size={18}
                  className={`shrink-0 transition-opacity ${
                    active ? "opacity-100" : "opacity-70"
                  }`}
                />
                {!collapsed && (
                  <span className="whitespace-nowrap">{item.label}</span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Separator */}
        <div className="mx-3 border-t border-border" />

        {/* Bottom section */}
        <div className="p-2 space-y-0.5">
          {/* Command palette trigger */}
          <button
            onClick={openCommandPalette}
            title={collapsed ? "Search (Cmd+K)" : undefined}
            className={`w-full flex items-center py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded-md transition-colors ${
              collapsed ? "justify-center px-0" : "justify-between px-3"
            }`}
          >
            {collapsed ? (
              <Command
                size={18}
                className="opacity-70 shrink-0"
              />
            ) : (
              <>
                <span className="flex items-center gap-3">
                  <Command size={18} className="opacity-70 shrink-0" />
                  <span className="whitespace-nowrap">Search</span>
                </span>
                <kbd className="text-[10px] font-mono bg-muted/50 px-1.5 py-0.5 rounded">
                  {typeof navigator !== "undefined" &&
                  /Mac/.test(navigator.userAgent)
                    ? "\u2318"
                    : "Ctrl+"}
                  K
                </kbd>
              </>
            )}
          </button>

          {/* Settings */}
          {(() => {
            const active = isActive("/settings");
            return (
              <Link
                href="/settings"
                title={collapsed ? "Settings" : undefined}
                className={`flex items-center gap-3 py-2 text-sm rounded-md transition-colors ${
                  collapsed ? "justify-center px-0" : "px-3"
                } ${
                  active
                    ? "bg-accent/10 text-foreground border-l-[3px] border-accent"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50 border-l-[3px] border-transparent"
                }`}
              >
                <Settings
                  size={18}
                  className={`shrink-0 transition-opacity ${
                    active ? "opacity-100" : "opacity-70"
                  }`}
                />
                {!collapsed && (
                  <span className="whitespace-nowrap">Settings</span>
                )}
              </Link>
            );
          })()}

          {/* Sign out */}
          <button
            onClick={handleSignOut}
            title={collapsed ? "Sign Out" : undefined}
            className={`w-full flex items-center gap-3 py-2 text-sm text-muted-foreground hover:text-destructive hover:bg-muted/50 rounded-md transition-colors ${
              collapsed ? "justify-center px-0" : "px-3"
            } border-l-[3px] border-transparent`}
          >
            <LogOut size={18} className="opacity-70 shrink-0" />
            {!collapsed && (
              <span className="whitespace-nowrap">Sign Out</span>
            )}
          </button>

          {/* Collapse toggle */}
          <button
            onClick={toggleCollapsed}
            className={`w-full flex items-center py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded-md transition-colors ${
              collapsed ? "justify-center px-0" : "justify-between px-3"
            }`}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? (
              <ChevronRight size={18} className="opacity-70 shrink-0" />
            ) : (
              <>
                <span className="whitespace-nowrap">Collapse</span>
                <ChevronLeft size={18} className="opacity-70 shrink-0" />
              </>
            )}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <div className="p-6 lg:p-8 max-w-screen-2xl mx-auto">{children}</div>
      </main>
    </div>
  );
}
