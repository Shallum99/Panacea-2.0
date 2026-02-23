"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { getApplications, type Application } from "@/lib/api/applications";
import {
  CheckCircle,
  Send,
  Eye,
  Inbox,
  ArrowRight,
  Zap,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_DOT_COLORS: Record<string, string> = {
  message_generated: "bg-blue-400",
  approved: "bg-amber-400",
  sent: "bg-green-400",
  opened: "bg-emerald-400",
  replied: "bg-accent",
};

const STATUS_FILTERS = [
  { value: "", label: "All" },
  { value: "message_generated", label: "Generated" },
  { value: "approved", label: "Approved" },
  { value: "sent", label: "Sent" },
  { value: "opened", label: "Opened" },
  { value: "replied", label: "Replied" },
  { value: "failed", label: "Failed" },
];

const BOARD_COLUMNS: { status: string; label: string }[] = [
  { status: "message_generated", label: "Generated" },
  { status: "approved", label: "Approved" },
  { status: "sent", label: "Sent" },
  { status: "opened", label: "Opened" },
  { status: "replied", label: "Replied" },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(dateStr: string | null) {
  if (!dateStr) return "";
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function truncateEmail(email: string | null, max = 24): string {
  if (!email) return "";
  if (email.length <= max) return email;
  return email.slice(0, max - 1) + "\u2026";
}



function BoardCardAction({ app }: { app: Application }) {
  switch (app.status) {
    case "message_generated":
      return (
        <span className="text-[10px] text-accent hover:underline">Review</span>
      );
    case "approved":
      return (
        <span className="text-[10px] font-medium text-accent hover:underline flex items-center gap-0.5">
          <Send className="w-2.5 h-2.5" />
          Send
        </span>
      );
    case "sent":
      return (
        <span className="text-[10px] text-muted-foreground/50">
          Awaiting...
        </span>
      );
    case "opened":
      return (
        <span className="text-[10px] text-emerald-400 hover:underline">
          Follow up
        </span>
      );
    case "replied":
      return (
        <span className="text-[10px] text-success hover:underline">View</span>
      );
    default:
      return null;
  }
}

function SummaryBanner({
  applications,
  onFilterChange,
}: {
  applications: Application[];
  onFilterChange: (status: string) => void;
}) {
  const readyToSend = applications.filter(
    (a) => a.status === "message_generated" || a.status === "approved"
  ).length;
  const opened = applications.filter((a) => a.status === "opened").length;
  const allSentOrWaiting =
    applications.length > 0 &&
    readyToSend === 0 &&
    opened === 0 &&
    applications.every((a) =>
      ["sent", "delivered", "sending", "replied"].includes(a.status)
    );

  if (readyToSend === 0 && opened === 0 && !allSentOrWaiting) return null;

  return (
    <div className="space-y-2">
      {readyToSend > 0 && (
        <button
          onClick={() => onFilterChange("approved")}
          className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg bg-card border-l-2 border-accent text-left transition-colors hover:bg-card-hover"
        >
          <Zap className="w-3.5 h-3.5 text-accent shrink-0" />
          <span className="text-xs text-foreground">
            <span className="font-medium">{readyToSend} application{readyToSend !== 1 ? "s" : ""}</span>{" "}
            <span className="text-muted-foreground">ready to send</span>
          </span>
          <ArrowRight className="w-3 h-3 text-muted-foreground ml-auto" />
        </button>
      )}
      {opened > 0 && (
        <button
          onClick={() => onFilterChange("opened")}
          className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg bg-card border-l-2 border-emerald-400 text-left transition-colors hover:bg-card-hover"
        >
          <Eye className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
          <span className="text-xs text-foreground">
            <span className="font-medium">{opened} email{opened !== 1 ? "s" : ""} opened</span>{" "}
            <span className="text-muted-foreground">&mdash; consider following up</span>
          </span>
          <ArrowRight className="w-3 h-3 text-muted-foreground ml-auto" />
        </button>
      )}
      {allSentOrWaiting && (
        <div className="flex items-center gap-3 px-4 py-2.5 rounded-lg bg-card border-l-2 border-success">
          <CheckCircle className="w-3.5 h-3.5 text-success shrink-0" />
          <span className="text-xs text-muted-foreground">
            All caught up! Your applications are in progress.
          </span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function EmptyState({ hasFilter }: { hasFilter: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-muted/60 mb-5">
        <Inbox className="w-8 h-8 text-muted-foreground" />
      </div>
      <p className="text-sm text-muted-foreground mb-1">
        {hasFilter
          ? "No applications match this filter."
          : "No applications yet."}
      </p>
      <p className="text-xs text-muted-foreground mb-5">
        {hasFilter
          ? "Try a different status or clear the filter."
          : "Generate your first outreach message to get started."}
      </p>
      <Link
        href="/generate"
        className="btn-gradient inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-lg"
      >
        New Application
      </Link>
    </div>
  );
}

function BoardCard({ app }: { app: Application }) {
  return (
    <Link
      href={`/applications/${app.id}`}
      className="card-elevated block p-3.5 space-y-2"
    >
      <p className="text-sm font-medium truncate">
        {app.company_name || "Untitled"}
      </p>
      {app.position_title && (
        <p className="text-xs text-muted-foreground truncate">
          {app.position_title}
        </p>
      )}
      <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-1">
        <span>{truncateEmail(app.recipient_email)}</span>
        <span className="shrink-0 ml-2">{formatDate(app.created_at)}</span>
      </div>
      <div className="pt-0.5">
        <BoardCardAction app={app} />
      </div>
    </Link>
  );
}

function BoardView({ applications }: { applications: Application[] }) {
  const grouped: Record<string, Application[]> = {};
  for (const col of BOARD_COLUMNS) {
    grouped[col.status] = [];
  }
  for (const app of applications) {
    // Map delivering/sent/delivered into sent column
    const normalized =
      app.status === "sending" || app.status === "delivered"
        ? "sent"
        : app.status;
    if (grouped[normalized]) {
      grouped[normalized].push(app);
    }
  }

  return (
    <div className="flex gap-4 overflow-x-auto pb-4 -mx-2 px-2">
      {BOARD_COLUMNS.map((col) => {
        const items = grouped[col.status];
        return (
          <div
            key={col.status}
            className="flex-shrink-0 w-64 min-w-[16rem] flex flex-col"
          >
            {/* Column header */}
            <div className="flex items-center gap-2 px-3 py-2.5 mb-3">
              <span
                className={`w-2 h-2 rounded-full ${STATUS_DOT_COLORS[col.status] || "bg-muted-foreground"}`}
              />
              <span className="text-xs font-semibold uppercase tracking-wider text-foreground">
                {col.label}
              </span>
              <span className="ml-auto text-[11px] font-medium text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                {items.length}
              </span>
            </div>
            {/* Column body */}
            <div className="flex-1 space-y-2.5 rounded-xl bg-card/50 p-2.5 min-h-[12rem]">
              {items.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-8 opacity-50">
                  No applications
                </p>
              ) : (
                items.map((app) => <BoardCard key={app.id} app={app} />)
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ApplicationsPage() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");

  useEffect(() => {
    loadApplications();
  }, [statusFilter]);

  async function loadApplications() {
    setLoading(true);
    try {
      const data = await getApplications(statusFilter || undefined);
      setApplications(data);
    } catch {
      toast.error("Failed to load applications");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Applications</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {applications.length} application
            {applications.length !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/generate"
            className="btn-gradient px-4 py-2 text-sm font-medium rounded-lg"
          >
            New Application
          </Link>
        </div>
      </div>

      {/* Status filter pills */}
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setStatusFilter(f.value)}
            className={`px-3 py-1.5 text-xs rounded-md border whitespace-nowrap transition-all ${
              statusFilter === f.value
                ? "btn-gradient border-transparent font-medium"
                : "border-border text-muted-foreground hover:text-foreground hover:border-muted-foreground"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Summary banner */}
      {!loading && applications.length > 0 && (
        <SummaryBanner
          applications={applications}
          onFilterChange={setStatusFilter}
        />
      )}

      {/* Content area */}
      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="border border-border rounded-lg p-4 animate-pulse"
            >
              <div className="flex items-center justify-between">
                <div className="space-y-2">
                  <div className="h-4 bg-muted rounded w-40" />
                  <div className="h-3 bg-muted rounded w-24" />
                </div>
                <div className="h-5 bg-muted rounded w-20" />
              </div>
            </div>
          ))}
        </div>
      ) : applications.length === 0 ? (
        <EmptyState hasFilter={!!statusFilter} />
      ) : (
        <BoardView applications={applications} />
      )}
    </div>
  );
}
