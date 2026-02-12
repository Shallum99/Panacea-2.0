"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import CommandPalette from "@/components/CommandPalette";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import { useTheme } from "@/hooks/useTheme";

const nav = [
  { href: "/dashboard", label: "Dashboard", icon: "H" },
  { href: "/jobs", label: "Jobs", icon: "J" },
  { href: "/profile", label: "Profile", icon: "P" },
  { href: "/resumes", label: "Resumes", icon: "R" },
  { href: "/generate", label: "Generate", icon: "G" },
  { href: "/applications", label: "Applications", icon: "A" },
  { href: "/pricing", label: "Pricing", icon: "$" },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const supabase = createClient();
  const { theme, toggle } = useTheme();

  useKeyboardShortcuts();

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.push("/login");
  }

  return (
    <div className="flex h-screen">
      <CommandPalette />

      {/* Sidebar */}
      <aside className="w-56 border-r border-border flex flex-col shrink-0">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <Link href="/dashboard" className="text-lg font-bold tracking-tight">
            Panacea
          </Link>
          <button
            onClick={toggle}
            className="w-7 h-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="5" />
                <line x1="12" y1="1" x2="12" y2="3" />
                <line x1="12" y1="21" x2="12" y2="23" />
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                <line x1="1" y1="12" x2="3" y2="12" />
                <line x1="21" y1="12" x2="23" y2="12" />
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            )}
          </button>
        </div>

        <nav className="flex-1 p-2 space-y-0.5">
          {nav.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2 text-sm rounded-md transition-colors ${
                  isActive
                    ? "bg-muted text-foreground"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                }`}
              >
                <span className="w-5 h-5 flex items-center justify-center text-xs font-mono opacity-50">
                  {item.icon}
                </span>
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Bottom: Cmd+K hint + Settings + Sign Out */}
        <div className="p-2 border-t border-border space-y-0.5">
          <button
            onClick={() => {
              document.dispatchEvent(
                new KeyboardEvent("keydown", { key: "k", metaKey: true })
              );
            }}
            className="w-full flex items-center justify-between px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded-md transition-colors"
          >
            <span>Search</span>
            <kbd className="text-[10px] font-mono bg-muted/50 px-1.5 py-0.5 rounded">
              {typeof navigator !== "undefined" && /Mac/.test(navigator.userAgent) ? "⌘" : "Ctrl+"}K
            </kbd>
          </button>
          <Link
            href="/settings"
            className={`flex items-center gap-3 px-3 py-2 text-sm rounded-md transition-colors ${
              pathname === "/settings"
                ? "bg-muted text-foreground"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
            }`}
          >
            <span className="w-5 h-5 flex items-center justify-center text-xs font-mono opacity-50">
              S
            </span>
            Settings
          </Link>
          <button
            onClick={handleSignOut}
            className="w-full flex items-center gap-3 px-3 py-2 text-sm text-muted-foreground hover:text-destructive hover:bg-muted/50 rounded-md transition-colors"
          >
            <span className="w-5 h-5 flex items-center justify-center text-xs font-mono opacity-50">
              Q
            </span>
            Sign Out
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
