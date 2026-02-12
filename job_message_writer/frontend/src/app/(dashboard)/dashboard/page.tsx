"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getResumes } from "@/lib/api/resumes";
import { getApplications, Application } from "@/lib/api/applications";
import {
  FileText,
  Send,
  Mail,
  MessageCircle,
  Sparkles,
  LayoutList,
  Upload,
  Inbox,
  CheckCircle2,
} from "lucide-react";
import {
  AreaChart,
  Area,
  ResponsiveContainer,
} from "recharts";

interface Stats {
  resumes: number;
  applications: number;
  sent: number;
  replies: number;
}

// Mock sparkline data for each stat card
const SPARKLINE_DATA: Record<string, number[]> = {
  resumes: [1, 1, 2, 2, 3, 3, 4],
  applications: [2, 3, 5, 4, 7, 8, 6],
  sent: [1, 2, 3, 2, 5, 6, 5],
  replies: [0, 1, 1, 2, 1, 3, 2],
};

const STAT_ICONS: Record<string, React.ReactNode> = {
  Resumes: <FileText className="w-4 h-4" />,
  Applications: <Send className="w-4 h-4" />,
  Sent: <Mail className="w-4 h-4" />,
  Replies: <MessageCircle className="w-4 h-4" />,
};

const STEPS = [
  {
    label: "Upload Resume",
    desc: "Upload your resume PDF to get started",
    href: "/resumes/upload",
    cta: "Upload",
  },
  {
    label: "Generate & Tailor",
    desc: "Create a message and optimize your resume for a job",
    href: "/generate",
    cta: "Get started",
  },
];

const QUICK_ACTIONS = [
  {
    label: "Generate & Tailor",
    href: "/generate",
    desc: "Create a message or optimize your resume",
    icon: <Sparkles className="w-5 h-5" />,
  },
  {
    label: "Applications",
    href: "/applications",
    desc: "View all your applications",
    icon: <LayoutList className="w-5 h-5" />,
  },
  {
    label: "Upload Resume",
    href: "/resumes/upload",
    desc: "Add a new resume",
    icon: <Upload className="w-5 h-5" />,
  },
];

function MiniSparkline({ dataKey, data }: { dataKey: string; data: number[] }) {
  const chartData = data.map((v, i) => ({ idx: i, value: v }));

  return (
    <div className="w-[80px] h-[30px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={`sparkFill-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.1} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="value"
            stroke="var(--accent)"
            strokeWidth={1.5}
            fill={`url(#sparkFill-${dataKey})`}
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
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
  const sparkData = SPARKLINE_DATA[label.toLowerCase()] || [0, 1, 2, 1, 3, 2, 4];

  return (
    <div className="card-elevated p-4">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <div className="text-accent">
              {STAT_ICONS[label]}
            </div>
          </div>
          {loading ? (
            <div className="h-8 w-12 bg-muted animate-pulse rounded" />
          ) : (
            <p className="text-2xl font-bold tracking-tight">{value}</p>
          )}
          <p className="text-xs text-muted-foreground mt-1">{label}</p>
        </div>
        <MiniSparkline dataKey={label.toLowerCase()} data={sparkData} />
      </div>
    </div>
  );
}

function GettingStarted({ stats, loading }: { stats: Stats; loading: boolean }) {
  const completedSteps = [
    stats.resumes > 0,
    stats.applications > 0,
  ];

  // Find first incomplete step
  const currentStep = completedSteps[0] ? 1 : 0;

  if (loading) {
    return (
      <div className="card-elevated p-6 animate-pulse">
        <div className="h-5 bg-muted rounded w-40 mb-4" />
        <div className="flex gap-4">
          {[1, 2].map((i) => (
            <div key={i} className="flex-1 h-20 bg-muted/30 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  // All steps done -- don't show stepper
  if (completedSteps[0] && completedSteps[1]) return null;

  return (
    <div className="card-elevated p-6">
      <h2 className="text-sm font-medium mb-5">Getting Started</h2>
      <div className="flex items-start gap-0">
        {STEPS.map((step, i) => {
          const isDone = completedSteps[i];
          const isCurrent = i === currentStep;
          const isLocked = i > 0 && !completedSteps[i - 1];

          return (
            <div key={i} className="flex-1 flex items-start">
              {/* Connector line */}
              {i > 0 && (
                <div className="flex items-center pt-3 -mx-1">
                  <div
                    className={`w-10 h-0.5 rounded-full transition-colors ${
                      completedSteps[i - 1]
                        ? "bg-gradient-to-r from-accent to-accent-secondary"
                        : "bg-border"
                    }`}
                  />
                </div>
              )}
              <div
                className={`flex-1 rounded-lg border p-4 transition-colors ${
                  isDone
                    ? "border-accent/30 bg-accent/5"
                    : isCurrent
                    ? "border-accent/50 bg-accent/5"
                    : "border-border"
                }`}
              >
                <div className="flex items-center gap-2.5 mb-2">
                  <div
                    className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold shrink-0 ${
                      isDone
                        ? "btn-gradient"
                        : isCurrent
                        ? "border-2 border-accent text-accent"
                        : "border border-border text-muted-foreground"
                    }`}
                  >
                    {isDone ? (
                      <CheckCircle2 className="w-3.5 h-3.5" />
                    ) : (
                      i + 1
                    )}
                  </div>
                  <span
                    className={`text-sm font-medium ${
                      isDone
                        ? "text-accent"
                        : isCurrent
                        ? "text-foreground"
                        : "text-muted-foreground"
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mb-3 ml-8.5">
                  {step.desc}
                </p>
                <div className="ml-8.5">
                  {isDone ? (
                    <span className="text-[10px] text-accent font-medium uppercase tracking-wider">
                      Completed
                    </span>
                  ) : isLocked ? (
                    <span className="text-[10px] text-muted-foreground">
                      Complete previous step
                    </span>
                  ) : (
                    <Link
                      href={step.href}
                      className="inline-flex items-center gap-1 text-xs font-medium btn-gradient px-3 py-1.5 rounded-md"
                    >
                      {step.cta}
                      <span aria-hidden="true">&rarr;</span>
                    </Link>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
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

const STATUS_DOT_COLORS: Record<string, string> = {
  draft: "bg-muted-foreground",
  message_generated: "bg-blue-400",
  approved: "bg-yellow-400",
  sent: "bg-accent",
  delivered: "bg-accent",
  opened: "bg-green-400",
  replied: "bg-emerald-400",
  failed: "bg-destructive",
};

const STATUS_TEXT_COLORS: Record<string, string> = {
  draft: "text-muted-foreground",
  message_generated: "text-blue-400",
  approved: "text-yellow-400",
  sent: "text-accent",
  delivered: "text-accent",
  opened: "text-green-400",
  replied: "text-emerald-400",
  failed: "text-destructive",
};

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

  return (
    <div className="space-y-8 animate-fade-in">
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
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {QUICK_ACTIONS.map((action) => (
          <Link
            key={action.href}
            href={action.href}
            className="card-interactive p-4 group flex items-start gap-3"
          >
            <div className="text-accent mt-0.5 shrink-0 transition-transform group-hover:scale-110">
              {action.icon}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium group-hover:text-accent transition-colors">
                {action.label}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                {action.desc}
              </p>
            </div>
          </Link>
        ))}
      </div>

      {/* Recent Applications */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-muted-foreground">
            Recent Applications
          </h2>
          {recentApps.length > 0 && (
            <Link
              href="/applications"
              className="text-xs text-muted-foreground hover:text-accent transition-colors"
            >
              View all &rarr;
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
          <div className="card-elevated p-10 text-center">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-accent/10 mb-4">
              <Inbox className="w-6 h-6 text-accent" />
            </div>
            <p className="text-base font-medium mb-1">No applications yet</p>
            <p className="text-sm text-muted-foreground mb-5">
              Start by generating your first message for a job application.
            </p>
            <Link
              href="/generate"
              className="inline-flex items-center gap-2 btn-gradient px-5 py-2.5 rounded-lg text-sm font-medium"
            >
              <Sparkles className="w-4 h-4" />
              Generate your first message
            </Link>
          </div>
        ) : (
          <div className="card-elevated overflow-hidden">
            <div className="divide-y divide-border stagger-children">
              {recentApps.map((app) => (
                <Link
                  key={app.id}
                  href={`/applications/${app.id}`}
                  className="flex items-center justify-between px-4 py-3 hover:bg-card-hover transition-colors"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium truncate">
                      {app.company_name || "Unknown Company"}
                      {app.position_title && (
                        <span className="text-muted-foreground font-normal">
                          {" "}
                          &mdash; {app.position_title}
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {app.method === "email" ? "Email" : "URL"} application
                      {app.created_at && ` \u00B7 ${timeAgo(app.created_at)}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0 ml-3">
                    <span
                      className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                        STATUS_DOT_COLORS[app.status] || "bg-muted-foreground"
                      }`}
                    />
                    <span
                      className={`text-xs font-medium capitalize ${
                        STATUS_TEXT_COLORS[app.status] || "text-muted-foreground"
                      }`}
                    >
                      {app.status.replace("_", " ")}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Keyboard hint */}
      <div className="text-xs text-muted-foreground/50 text-center pt-4">
        Press{" "}
        <kbd className="font-mono bg-muted/30 px-1.5 py-0.5 rounded border border-border">
          {typeof navigator !== "undefined" && /Mac/.test(navigator.userAgent)
            ? "\u2318"
            : "Ctrl+"}
          K
        </kbd>{" "}
        to open command palette
      </div>
    </div>
  );
}
