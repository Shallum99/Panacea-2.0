"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getResumes } from "@/lib/api/resumes";
import { getApplications, Application } from "@/lib/api/applications";

interface Stats {
  resumes: number;
  applications: number;
  sent: number;
  replies: number;
}

const STEPS = [
  {
    label: "Upload Resume",
    desc: "Upload your resume PDF to get started",
    href: "/resumes/upload",
    cta: "Upload",
  },
  {
    label: "Generate Message",
    desc: "Create a tailored application message",
    href: "/generate",
    cta: "Generate",
  },
  {
    label: "Tailor Resume",
    desc: "Optimize your resume for a specific job",
    href: "/tailor",
    cta: "Tailor",
  },
];

function GettingStarted({ stats, loading }: { stats: Stats; loading: boolean }) {
  const completedSteps = [
    stats.resumes > 0,
    stats.applications > 0,
    false, // tailor is always "available", never marked done
  ];

  // Find first incomplete step
  const currentStep = completedSteps[0] ? (completedSteps[1] ? 2 : 1) : 0;

  if (loading) {
    return (
      <div className="border border-border rounded-lg p-6 animate-pulse">
        <div className="h-5 bg-muted rounded w-40 mb-4" />
        <div className="flex gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex-1 h-20 bg-muted/30 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  // All steps done (both resumes and applications exist) — don't show stepper
  if (completedSteps[0] && completedSteps[1]) return null;

  return (
    <div className="border border-border rounded-lg p-6">
      <h2 className="text-sm font-medium mb-4">Getting Started</h2>
      <div className="flex items-start gap-3">
        {STEPS.map((step, i) => {
          const isDone = completedSteps[i];
          const isCurrent = i === currentStep;
          const isLocked = i > 0 && !completedSteps[i - 1];

          return (
            <div key={i} className="flex-1 flex items-start gap-3">
              {/* Connector line */}
              {i > 0 && (
                <div className={`w-8 h-px mt-4 shrink-0 -ml-3 -mr-1 ${
                  completedSteps[i - 1] ? "bg-accent" : "bg-border"
                }`} />
              )}
              <div className={`flex-1 rounded-lg border p-4 transition-colors ${
                isDone
                  ? "border-accent/30 bg-accent/5"
                  : isCurrent
                  ? "border-accent/50 bg-accent/5"
                  : "border-border"
              }`}>
                <div className="flex items-center gap-2 mb-1.5">
                  <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 ${
                    isDone
                      ? "bg-accent text-accent-foreground"
                      : isCurrent
                      ? "border-2 border-accent text-accent"
                      : "border border-border text-muted-foreground"
                  }`}>
                    {isDone ? (
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    ) : (
                      i + 1
                    )}
                  </div>
                  <span className={`text-sm font-medium ${
                    isDone ? "text-accent" : isCurrent ? "text-foreground" : "text-muted-foreground"
                  }`}>
                    {step.label}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mb-3">{step.desc}</p>
                {isDone ? (
                  <span className="text-[10px] text-accent font-medium">Done</span>
                ) : isLocked ? (
                  <span className="text-[10px] text-muted-foreground">Complete previous step</span>
                ) : (
                  <Link
                    href={step.href}
                    className="inline-block text-xs font-medium text-accent hover:text-accent/80 transition-colors"
                  >
                    {step.cta} &rarr;
                  </Link>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  loading,
}: {
  label: string;
  value: number;
  loading: boolean;
}) {
  return (
    <div className="p-4 border border-border rounded-lg">
      {loading ? (
        <div className="h-8 w-12 bg-muted animate-pulse rounded" />
      ) : (
        <p className="text-2xl font-bold">{value}</p>
      )}
      <p className="text-xs text-muted-foreground mt-1">{label}</p>
    </div>
  );
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats>({
    resumes: 0,
    applications: 0,
    sent: 0,
    replies: 0,
  });
  const [recentApps, setRecentApps] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [resumes, applications] = await Promise.all([
          getResumes().catch(() => []),
          getApplications().catch(() => []),
        ]);

        const sent = applications.filter(
          (a) => a.sent_at || ["sent", "delivered", "opened", "replied"].includes(a.status)
        ).length;
        const replies = applications.filter(
          (a) => a.replied_at || a.status === "replied"
        ).length;

        setStats({
          resumes: resumes.length,
          applications: applications.length,
          sent,
          replies,
        });

        // Most recent 5 applications
        const sorted = [...applications].sort(
          (a, b) =>
            new Date(b.created_at || 0).getTime() -
            new Date(a.created_at || 0).getTime()
        );
        setRecentApps(sorted.slice(0, 5));
      } catch {
        // silently fail
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const statusColor: Record<string, string> = {
    draft: "text-muted-foreground",
    message_generated: "text-blue-400",
    approved: "text-yellow-400",
    sent: "text-accent",
    delivered: "text-accent",
    opened: "text-green-400",
    replied: "text-emerald-400",
    failed: "text-destructive",
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Overview of your job applications
        </p>
      </div>

      {/* Getting Started Stepper */}
      <GettingStarted stats={stats} loading={loading} />

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard label="Resumes" value={stats.resumes} loading={loading} />
        <StatCard label="Applications" value={stats.applications} loading={loading} />
        <StatCard label="Sent" value={stats.sent} loading={loading} />
        <StatCard label="Replies" value={stats.replies} loading={loading} />
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "Generate Message", href: "/generate", desc: "Create a tailored application" },
          { label: "Tailor Resume", href: "/tailor", desc: "Optimize for a job description" },
          { label: "Upload Resume", href: "/resumes/upload", desc: "Add a new resume" },
        ].map((action) => (
          <Link
            key={action.href}
            href={action.href}
            className="p-4 border border-border rounded-lg hover:border-muted-foreground/30 transition-colors group"
          >
            <p className="text-sm font-medium group-hover:text-accent transition-colors">
              {action.label}
            </p>
            <p className="text-xs text-muted-foreground mt-1">{action.desc}</p>
          </Link>
        ))}
      </div>

      {/* Recent Applications */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-muted-foreground">Recent Applications</h2>
          {recentApps.length > 0 && (
            <Link
              href="/applications"
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              View all
            </Link>
          )}
        </div>

        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-14 bg-muted/30 animate-pulse rounded-lg"
              />
            ))}
          </div>
        ) : recentApps.length === 0 ? (
          <div className="border border-border rounded-lg p-8 text-center">
            <p className="text-sm text-muted-foreground">
              No applications yet.{" "}
              <Link href="/generate" className="text-accent hover:underline">
                Generate your first message
              </Link>
            </p>
          </div>
        ) : (
          <div className="border border-border rounded-lg divide-y divide-border">
            {recentApps.map((app) => (
              <Link
                key={app.id}
                href={`/applications/${app.id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-muted/30 transition-colors"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">
                    {app.company_name || "Unknown Company"}
                    {app.position_title && (
                      <span className="text-muted-foreground font-normal">
                        {" "}
                        — {app.position_title}
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {app.method === "email" ? "Email" : "URL"} application
                    {app.created_at && ` · ${timeAgo(app.created_at)}`}
                  </p>
                </div>
                <span
                  className={`text-xs font-medium capitalize ${
                    statusColor[app.status] || "text-muted-foreground"
                  }`}
                >
                  {app.status.replace("_", " ")}
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Keyboard hint */}
      <div className="text-xs text-muted-foreground/50 text-center pt-4">
        Press{" "}
        <kbd className="font-mono bg-muted/30 px-1 py-0.5 rounded">
          {typeof navigator !== "undefined" && /Mac/.test(navigator.userAgent) ? "⌘" : "Ctrl+"}K
        </kbd>{" "}
        to open command palette
      </div>
    </div>
  );
}
