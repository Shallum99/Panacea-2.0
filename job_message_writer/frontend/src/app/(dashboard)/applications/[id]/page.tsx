"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  getApplication,
  updateApplication,
  approveApplication,
  sendApplication,
  deleteApplication,
  type Application,
} from "@/lib/api/applications";

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

function formatDate(dateStr: string | null) {
  if (!dateStr) return null;
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function ApplicationDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params.id);

  const [app, setApp] = useState<Application | null>(null);
  const [loading, setLoading] = useState(true);
  const [editedMessage, setEditedMessage] = useState("");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await getApplication(id);
      setApp(data);
      setEditedMessage(data.edited_message || data.generated_message || "");
      setRecipientEmail(data.recipient_email || "");
    } catch {
      toast.error("Application not found");
      router.push("/applications");
    } finally {
      setLoading(false);
    }
  }, [id, router]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSave() {
    if (!app) return;
    setSaving(true);
    try {
      const updated = await updateApplication(app.id, {
        edited_message: editedMessage,
        recipient_email: recipientEmail || undefined,
      });
      setApp(updated);
      setIsEditing(false);
      toast.success("Changes saved");
    } catch {
      toast.error("Failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function handleApprove() {
    if (!app) return;
    // Save any pending edits first
    if (isEditing) {
      await handleSave();
    }
    try {
      const updated = await approveApplication(app.id);
      setApp(updated);
      toast.success("Application approved");
    } catch {
      toast.error("Failed to approve");
    }
  }

  async function handleSend() {
    if (!app) return;
    if (!recipientEmail) {
      toast.error("Add a recipient email first");
      return;
    }
    // Save email if changed
    if (recipientEmail !== app.recipient_email) {
      await updateApplication(app.id, { recipient_email: recipientEmail });
    }
    setSending(true);
    try {
      const updated = await sendApplication(app.id);
      setApp(updated);
      if (updated.status === "sent") {
        toast.success("Email sent successfully");
      } else {
        toast.error("Email sending failed");
      }
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response
              ?.data?.detail
          : undefined;
      toast.error(msg || "Failed to send email");
    } finally {
      setSending(false);
    }
  }

  async function handleDelete() {
    if (!app) return;
    try {
      await deleteApplication(app.id);
      toast.success("Application deleted");
      router.push("/applications");
    } catch {
      toast.error("Failed to delete");
    }
  }

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-6 bg-muted rounded w-1/3" />
        <div className="h-4 bg-muted rounded w-1/4" />
        <div className="border border-border rounded-lg p-6 space-y-3">
          <div className="h-3 bg-muted rounded w-full" />
          <div className="h-3 bg-muted rounded w-5/6" />
          <div className="h-3 bg-muted rounded w-4/6" />
        </div>
      </div>
    );
  }

  if (!app) return null;

  const canEdit = ["draft", "message_generated", "approved"].includes(app.status);
  const canSend = ["message_generated", "approved"].includes(app.status);
  const isSent = ["sent", "delivered", "opened", "replied"].includes(app.status);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <button
            onClick={() => router.push("/applications")}
            className="text-xs text-muted-foreground hover:text-foreground mb-2 transition-colors"
          >
            &larr; Applications
          </button>
          <h1 className="text-2xl font-bold tracking-tight">
            {app.company_name || "Untitled Application"}
          </h1>
          <div className="flex items-center gap-3 mt-1">
            {app.position_title && (
              <span className="text-sm text-muted-foreground">
                {app.position_title}
              </span>
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
        <button
          onClick={handleDelete}
          className="text-xs text-muted-foreground hover:text-red-400 transition-colors"
        >
          Delete
        </button>
      </div>

      {/* Email tracking timeline */}
      {isSent && (
        <div className="border border-border rounded-lg p-4">
          <p className="text-xs font-medium text-muted-foreground mb-3">
            Email Tracking
          </p>
          <div className="flex items-center gap-4">
            {[
              { label: "Sent", date: app.sent_at, active: !!app.sent_at },
              {
                label: "Delivered",
                date: null,
                active: app.status === "delivered" || !!app.opened_at,
              },
              { label: "Opened", date: app.opened_at, active: !!app.opened_at },
              {
                label: "Replied",
                date: app.replied_at,
                active: !!app.replied_at,
              },
            ].map((step, i) => (
              <div key={step.label} className="flex items-center gap-4">
                {i > 0 && (
                  <div
                    className={`w-8 h-px ${
                      step.active ? "bg-accent" : "bg-border"
                    }`}
                  />
                )}
                <div className="text-center">
                  <div
                    className={`w-2.5 h-2.5 rounded-full mx-auto mb-1 ${
                      step.active ? "bg-accent" : "bg-border"
                    }`}
                  />
                  <p
                    className={`text-[10px] ${
                      step.active
                        ? "text-foreground font-medium"
                        : "text-muted-foreground"
                    }`}
                  >
                    {step.label}
                  </p>
                  {step.date && (
                    <p className="text-[9px] text-muted-foreground">
                      {formatDate(step.date)}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Message — main panel */}
        <div className="lg:col-span-2 space-y-4">
          <div className="border border-border rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <p className="text-xs font-medium text-muted-foreground">
                Message
              </p>
              {canEdit && !isEditing && (
                <button
                  onClick={() => setIsEditing(true)}
                  className="text-xs text-accent hover:underline"
                >
                  Edit
                </button>
              )}
            </div>
            {isEditing ? (
              <div>
                <textarea
                  value={editedMessage}
                  onChange={(e) => setEditedMessage(e.target.value)}
                  rows={18}
                  className="w-full px-4 py-3 text-sm bg-background border-none focus:outline-none resize-y font-mono leading-relaxed"
                />
                <div className="px-4 py-3 border-t border-border flex items-center gap-2">
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    className="px-3 py-1.5 text-xs font-medium bg-accent text-accent-foreground rounded-md hover:opacity-90 disabled:opacity-40"
                  >
                    {saving ? "Saving..." : "Save"}
                  </button>
                  <button
                    onClick={() => {
                      setEditedMessage(
                        app.edited_message || app.generated_message || ""
                      );
                      setIsEditing(false);
                    }}
                    className="px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="px-4 py-3">
                <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed text-foreground/90">
                  {app.final_message ||
                    app.edited_message ||
                    app.generated_message}
                </pre>
              </div>
            )}
          </div>

          {/* Actions */}
          {canSend && (
            <div className="flex items-center gap-2">
              {app.status !== "approved" && (
                <button
                  onClick={handleApprove}
                  className="px-4 py-2 text-sm font-medium border border-accent text-accent rounded-md hover:bg-accent/10 transition-colors"
                >
                  Approve
                </button>
              )}
              <button
                onClick={handleSend}
                disabled={sending || !recipientEmail}
                className="px-4 py-2 text-sm font-medium bg-accent text-accent-foreground rounded-md hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {sending ? "Sending..." : "Send Email"}
              </button>
            </div>
          )}
        </div>

        {/* Sidebar — details */}
        <div className="space-y-4">
          {/* Recipient */}
          <div className="border border-border rounded-lg p-4 space-y-3">
            <p className="text-xs font-medium text-muted-foreground">
              Recipient
            </p>
            {canEdit ? (
              <input
                type="email"
                value={recipientEmail}
                onChange={(e) => setRecipientEmail(e.target.value)}
                placeholder="recruiter@company.com"
                className="w-full h-8 px-2 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted-foreground/50"
              />
            ) : (
              <p className="text-sm">
                {app.recipient_email || (
                  <span className="text-muted-foreground">None</span>
                )}
              </p>
            )}
          </div>

          {/* Details */}
          <div className="border border-border rounded-lg p-4 space-y-3">
            <p className="text-xs font-medium text-muted-foreground">Details</p>
            <div className="space-y-2 text-sm">
              {app.message_type && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Type</span>
                  <span>{app.message_type.replace("_", " ")}</span>
                </div>
              )}
              {app.method && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Method</span>
                  <span>{app.method}</span>
                </div>
              )}
              {app.job_url && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Job URL</span>
                  <a
                    href={app.job_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:underline truncate max-w-[160px]"
                  >
                    Link
                  </a>
                </div>
              )}
              {app.created_at && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Created</span>
                  <span className="text-xs">{formatDate(app.created_at)}</span>
                </div>
              )}
              {app.email_message_id && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Email ID</span>
                  <span className="text-[10px] font-mono truncate max-w-[140px]">
                    {app.email_message_id}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* ATS Scores */}
          {(app.ats_score_before !== null || app.ats_score_after !== null) && (
            <div className="border border-border rounded-lg p-4 space-y-3">
              <p className="text-xs font-medium text-muted-foreground">
                ATS Score
              </p>
              <div className="flex gap-4">
                {app.ats_score_before !== null && (
                  <div>
                    <p className="text-2xl font-bold">
                      {Math.round(app.ats_score_before)}
                    </p>
                    <p className="text-[10px] text-muted-foreground">Before</p>
                  </div>
                )}
                {app.ats_score_after !== null && (
                  <div>
                    <p className="text-2xl font-bold text-accent">
                      {Math.round(app.ats_score_after)}
                    </p>
                    <p className="text-[10px] text-muted-foreground">After</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
