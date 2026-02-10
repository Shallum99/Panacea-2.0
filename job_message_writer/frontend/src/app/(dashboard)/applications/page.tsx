"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { getApplications, type Application } from "@/lib/api/applications";

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-muted text-muted-foreground",
  message_generated: "bg-blue-500/10 text-blue-400",
  approved: "bg-amber-500/10 text-amber-400",
  sending: "bg-yellow-500/10 text-yellow-400",
  sent: "bg-green-500/10 text-green-400",
  delivered: "bg-green-500/10 text-green-400",
  opened: "bg-emerald-500/10 text-emerald-400",
  replied: "bg-accent/10 text-accent",
  failed: "bg-red-500/10 text-red-400",
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

function formatDate(dateStr: string | null) {
  if (!dateStr) return "";
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

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
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Applications</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {applications.length} application
            {applications.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Link
          href="/generate"
          className="px-4 py-2 bg-accent text-accent-foreground text-sm font-medium rounded-lg hover:opacity-90 transition-opacity"
        >
          New Application
        </Link>
      </div>

      {/* Status filters */}
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setStatusFilter(f.value)}
            className={`px-3 py-1.5 text-xs rounded-md border whitespace-nowrap transition-colors ${
              statusFilter === f.value
                ? "border-accent bg-accent/10 text-accent"
                : "border-border text-muted-foreground hover:text-foreground hover:border-muted-foreground"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

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
        <div className="border border-border rounded-lg p-12 text-center">
          <p className="text-sm text-muted-foreground">
            {statusFilter
              ? "No applications with this status."
              : "No applications yet."}
          </p>
          <Link
            href="/generate"
            className="inline-block mt-3 text-sm text-accent hover:underline"
          >
            Generate your first message
          </Link>
        </div>
      ) : (
        <div className="space-y-1.5">
          {applications.map((app) => (
            <Link
              key={app.id}
              href={`/applications/${app.id}`}
              className="block border border-border rounded-lg p-4 hover:border-muted-foreground transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="space-y-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium truncate">
                      {app.company_name || "Untitled"}
                    </p>
                    {app.position_title && (
                      <span className="text-xs text-muted-foreground truncate">
                        {app.position_title}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    {app.message_type && (
                      <span>{app.message_type.replace("_", " ")}</span>
                    )}
                    {app.recipient_email && <span>{app.recipient_email}</span>}
                    {app.created_at && <span>{formatDate(app.created_at)}</span>}
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  {/* Email tracking timeline */}
                  {app.sent_at && (
                    <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                      <span className="text-green-400">Sent</span>
                      {app.opened_at && (
                        <>
                          <span className="opacity-30">&rarr;</span>
                          <span className="text-emerald-400">Opened</span>
                        </>
                      )}
                      {app.replied_at && (
                        <>
                          <span className="opacity-30">&rarr;</span>
                          <span className="text-accent">Replied</span>
                        </>
                      )}
                    </div>
                  )}
                  <span
                    className={`text-[10px] font-medium px-2 py-0.5 rounded ${
                      STATUS_COLORS[app.status] || STATUS_COLORS.draft
                    }`}
                  >
                    {app.status.replace("_", " ")}
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
