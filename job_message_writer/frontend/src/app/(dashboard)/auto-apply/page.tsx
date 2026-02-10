"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { toast } from "sonner";
import { getResumes, type Resume } from "@/lib/api/resumes";
import {
  emailAutoApply,
  urlAutoApply,
  getAutoApplyStatus,
  cancelAutoApply,
  submitAutoApply,
  getScreenshotUrl,
  getWebSocketUrl,
  type AutoApplyStatus,
  type AutoApplyStep,
  type EmailAutoApplyResponse,
} from "@/lib/api/autoApply";
import { createClient } from "@/lib/supabase/client";

type Tab = "email" | "url";

const STEP_ICONS: Record<string, string> = {
  pending: "○",
  running: "◌",
  done: "●",
  failed: "✕",
};

export default function AutoApplyPage() {
  const [tab, setTab] = useState<Tab>("email");
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [loadingResumes, setLoadingResumes] = useState(true);
  const [selectedResumeId, setSelectedResumeId] = useState<number | undefined>();

  useEffect(() => {
    loadResumes();
  }, []);

  async function loadResumes() {
    try {
      const data = await getResumes();
      setResumes(data);
      const active = data.find((r) => r.is_active);
      if (active) setSelectedResumeId(active.id);
      else if (data.length > 0) setSelectedResumeId(data[0].id);
    } catch {
      toast.error("Failed to load resumes");
    } finally {
      setLoadingResumes(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Auto Apply</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Automatically apply to jobs via email or URL
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border">
        {(["email", "url"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t
                ? "border-accent text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t === "email" ? "Email" : "URL (Browser)"}
          </button>
        ))}
      </div>

      {/* Resume selector (shared) */}
      <div>
        <label className="block text-xs font-medium text-muted-foreground mb-1.5">
          Resume
        </label>
        {loadingResumes ? (
          <div className="h-9 bg-muted rounded-md animate-pulse w-64" />
        ) : resumes.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No resumes uploaded.{" "}
            <a href="/resumes/upload" className="text-accent hover:underline">
              Upload one
            </a>
          </p>
        ) : (
          <select
            value={selectedResumeId ?? ""}
            onChange={(e) => setSelectedResumeId(Number(e.target.value))}
            className="w-64 h-9 px-3 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent"
          >
            {resumes.map((r) => (
              <option key={r.id} value={r.id}>
                {r.title}
                {r.is_active ? " (Active)" : ""}
              </option>
            ))}
          </select>
        )}
      </div>

      {tab === "email" ? (
        <EmailTab resumeId={selectedResumeId} />
      ) : (
        <URLTab resumeId={selectedResumeId} />
      )}
    </div>
  );
}

// --- Email Tab ---

function EmailTab({ resumeId }: { resumeId?: number }) {
  const [jobDescription, setJobDescription] = useState("");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [positionTitle, setPositionTitle] = useState("");
  const [recruiterName, setRecruiterName] = useState("");
  const [optimizeResume, setOptimizeResume] = useState(true);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<EmailAutoApplyResponse | null>(null);

  async function handleSend() {
    if (!jobDescription.trim() || !recipientEmail.trim()) {
      toast.error("Job description and recipient email are required");
      return;
    }
    setSending(true);
    setResult(null);
    try {
      const res = await emailAutoApply({
        job_description: jobDescription,
        recipient_email: recipientEmail,
        resume_id: resumeId,
        position_title: positionTitle || undefined,
        recruiter_name: recruiterName || undefined,
        optimize_resume: optimizeResume,
      });
      setResult(res);
      if (res.status === "sent") {
        toast.success(`Email sent to ${recipientEmail}`);
      } else {
        toast.error("Email sending failed");
      }
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response
              ?.data?.detail
          : undefined;
      toast.error(msg || "Auto-apply failed");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">
              Recipient Email
            </label>
            <input
              type="email"
              value={recipientEmail}
              onChange={(e) => setRecipientEmail(e.target.value)}
              placeholder="recruiter@company.com"
              className="w-full h-9 px-3 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted-foreground/50"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">
              Position Title
            </label>
            <input
              value={positionTitle}
              onChange={(e) => setPositionTitle(e.target.value)}
              placeholder="e.g. Senior Engineer"
              className="w-full h-9 px-3 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted-foreground/50"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">
              Recruiter Name
            </label>
            <input
              value={recruiterName}
              onChange={(e) => setRecruiterName(e.target.value)}
              placeholder="Optional"
              className="w-full h-9 px-3 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted-foreground/50"
            />
          </div>
          <div className="flex items-end pb-1">
            <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
              <input
                type="checkbox"
                checked={optimizeResume}
                onChange={(e) => setOptimizeResume(e.target.checked)}
                className="rounded border-border"
              />
              Optimize resume for ATS
            </label>
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1.5">
            Job Description
          </label>
          <textarea
            value={jobDescription}
            onChange={(e) => setJobDescription(e.target.value)}
            rows={12}
            placeholder="Paste the full job description here..."
            className="w-full px-3 py-2 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted-foreground/50 resize-y"
          />
        </div>

        <button
          onClick={handleSend}
          disabled={sending || !jobDescription.trim() || !recipientEmail.trim()}
          className="w-full h-10 bg-accent text-accent-foreground text-sm font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {sending ? "Sending application..." : "Send Application Email"}
        </button>
      </div>

      {/* Result panel */}
      <div>
        {sending ? (
          <div className="border border-border rounded-lg p-8 text-center space-y-3">
            <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto" />
            <p className="text-sm text-muted-foreground">
              {optimizeResume
                ? "Optimizing resume & generating message..."
                : "Generating message & sending..."}
            </p>
          </div>
        ) : result ? (
          <div className="border border-border rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">{result.company_name}</p>
                <p className="text-xs text-muted-foreground">
                  {result.status === "sent" ? "Email sent" : "Failed to send"}
                </p>
              </div>
              <span
                className={`text-[10px] font-medium px-2 py-0.5 rounded ${
                  result.status === "sent"
                    ? "bg-green-500/10 text-green-400"
                    : "bg-red-500/10 text-red-400"
                }`}
              >
                {result.status}
              </span>
            </div>
            <div className="px-4 py-3 space-y-2">
              <p className="text-xs text-muted-foreground font-mono">
                {result.message_preview}
              </p>
              {result.resume_optimized && (
                <p className="text-[10px] text-accent">
                  Resume was optimized for ATS
                </p>
              )}
            </div>
            <div className="px-4 py-3 border-t border-border">
              <a
                href={`/applications/${result.application_id}`}
                className="text-xs text-accent hover:underline"
              >
                View Application Details
              </a>
            </div>
          </div>
        ) : (
          <div className="border border-dashed border-border rounded-lg p-12 flex items-center justify-center h-full min-h-[200px]">
            <div className="text-center">
              <p className="text-sm text-muted-foreground">
                Fill in the details and send
              </p>
              <p className="text-xs text-muted-foreground/60 mt-1">
                AI generates a tailored message, optionally optimizes your
                resume, and sends everything via email
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// --- URL Tab ---

function URLTab({ resumeId }: { resumeId?: number }) {
  const [jobUrl, setJobUrl] = useState("");
  const [coverLetter, setCoverLetter] = useState("");
  const [taskStatus, setTaskStatus] = useState<AutoApplyStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  const connectWebSocket = useCallback((taskId: string) => {
    const wsUrl = getWebSocketUrl(taskId);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setTaskStatus(data);
      } catch {
        // ignore
      }
    };

    ws.onerror = () => {
      // Fallback to polling
      ws.close();
      startPolling(taskId);
    };

    ws.onclose = () => {
      wsRef.current = null;
    };
  }, []);

  function startPolling(taskId: string) {
    if (pollingRef.current) clearInterval(pollingRef.current);
    pollingRef.current = setInterval(async () => {
      try {
        const status = await getAutoApplyStatus(taskId);
        setTaskStatus(status);
        if (["done", "failed", "cancelled", "review"].includes(status.status)) {
          if (pollingRef.current) clearInterval(pollingRef.current);
        }
      } catch {
        // ignore
      }
    }, 2000);
  }

  async function handleStart() {
    if (!jobUrl.trim()) {
      toast.error("Enter a job URL");
      return;
    }
    setStarting(true);
    setTaskStatus(null);
    try {
      const res = await urlAutoApply({
        job_url: jobUrl,
        resume_id: resumeId,
        cover_letter: coverLetter || undefined,
      });
      setTaskStatus(res);
      connectWebSocket(res.task_id);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response
              ?.data?.detail
          : undefined;
      toast.error(msg || "Failed to start auto-apply");
    } finally {
      setStarting(false);
    }
  }

  async function handleCancel() {
    if (!taskStatus) return;
    try {
      await cancelAutoApply(taskStatus.task_id);
      setTaskStatus((prev) => (prev ? { ...prev, status: "cancelled" } : null));
      toast.success("Task cancelled");
    } catch {
      toast.error("Failed to cancel");
    }
  }

  async function handleSubmit() {
    if (!taskStatus) return;
    try {
      const res = await submitAutoApply(taskStatus.task_id);
      setTaskStatus(res);
      toast.success("Application submitted");
    } catch {
      toast.error("Failed to submit");
    }
  }

  function handleReset() {
    if (wsRef.current) wsRef.current.close();
    if (pollingRef.current) clearInterval(pollingRef.current);
    setTaskStatus(null);
  }

  const isRunning = taskStatus?.status === "running";
  const isReview = taskStatus?.status === "review";
  const isDone = taskStatus?.status === "done";
  const isFailed = taskStatus?.status === "failed";

  return (
    <div className="space-y-4">
      {/* Input */}
      {!taskStatus && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                Job Application URL
              </label>
              <input
                value={jobUrl}
                onChange={(e) => setJobUrl(e.target.value)}
                placeholder="https://boards.greenhouse.io/company/jobs/12345"
                className="w-full h-9 px-3 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted-foreground/50"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                Cover Letter (optional)
              </label>
              <textarea
                value={coverLetter}
                onChange={(e) => setCoverLetter(e.target.value)}
                rows={6}
                placeholder="Optional cover letter to include..."
                className="w-full px-3 py-2 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted-foreground/50 resize-y"
              />
            </div>

            <button
              onClick={handleStart}
              disabled={starting || !jobUrl.trim()}
              className="w-full h-10 bg-accent text-accent-foreground text-sm font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {starting ? "Starting..." : "Start Auto-Apply"}
            </button>
          </div>

          <div className="border border-dashed border-border rounded-lg p-8 flex items-center justify-center">
            <div className="text-center space-y-3">
              <p className="text-sm font-medium">Browser Automation</p>
              <div className="text-xs text-muted-foreground space-y-2 text-left max-w-xs">
                <p>1. Enter the job application URL</p>
                <p>2. A headless browser navigates to the page</p>
                <p>3. AI analyzes the form and fills your details</p>
                <p>4. Review the filled form before submitting</p>
                <p>5. Screenshots at every step for transparency</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Progress */}
      {taskStatus && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">
                {isDone
                  ? "Application Submitted"
                  : isFailed
                  ? "Application Failed"
                  : isReview
                  ? "Ready for Review"
                  : "Applying..."}
              </p>
              <p className="text-xs text-muted-foreground truncate max-w-md">
                {taskStatus.job_url}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {isRunning && (
                <button
                  onClick={handleCancel}
                  className="px-3 py-1.5 text-xs text-red-400 border border-red-400/30 rounded-md hover:bg-red-400/10"
                >
                  Cancel
                </button>
              )}
              {isReview && (
                <button
                  onClick={handleSubmit}
                  className="px-3 py-1.5 text-xs bg-accent text-accent-foreground rounded-md hover:opacity-90"
                >
                  Confirm & Submit
                </button>
              )}
              {(isDone || isFailed) && (
                <button
                  onClick={handleReset}
                  className="px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
                >
                  Start Over
                </button>
              )}
            </div>
          </div>

          {/* Steps timeline */}
          <div className="space-y-2">
            {taskStatus.steps.map((step, i) => (
              <StepCard key={i} step={step} taskId={taskStatus.task_id} />
            ))}
          </div>

          {/* Error */}
          {taskStatus.error && (
            <div className="border border-red-400/30 bg-red-400/5 rounded-lg p-4">
              <p className="text-xs text-red-400">{taskStatus.error}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// --- Step Card ---

function StepCard({
  step,
  taskId,
}: {
  step: AutoApplyStep;
  taskId: string;
}) {
  const [showScreenshot, setShowScreenshot] = useState(false);

  // Extract filename from path
  const screenshotFilename = step.screenshot_path
    ? step.screenshot_path.split("/").pop() || ""
    : "";

  return (
    <div
      className={`border rounded-lg p-3 transition-colors ${
        step.status === "running"
          ? "border-accent/50 bg-accent/5"
          : step.status === "failed"
          ? "border-red-400/30"
          : "border-border"
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={`text-xs ${
              step.status === "running"
                ? "text-accent animate-pulse"
                : step.status === "done"
                ? "text-green-400"
                : step.status === "failed"
                ? "text-red-400"
                : "text-muted-foreground"
            }`}
          >
            {STEP_ICONS[step.status] || "○"}
          </span>
          <p className="text-sm font-medium">{step.name}</p>
        </div>
        {screenshotFilename && (
          <button
            onClick={() => setShowScreenshot(!showScreenshot)}
            className="text-[10px] text-accent hover:underline"
          >
            {showScreenshot ? "Hide" : "Screenshot"}
          </button>
        )}
      </div>
      {step.detail && (
        <p className="text-xs text-muted-foreground mt-1 ml-5">{step.detail}</p>
      )}
      {showScreenshot && screenshotFilename && (
        <div className="mt-2 ml-5">
          <img
            src={getScreenshotUrl(screenshotFilename)}
            alt={step.name}
            className="rounded border border-border max-h-64 w-auto"
          />
        </div>
      )}
    </div>
  );
}
