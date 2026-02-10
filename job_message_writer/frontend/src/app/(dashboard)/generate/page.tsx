"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { createClient } from "@/lib/supabase/client";
import { getResumes, type Resume } from "@/lib/api/resumes";
import {
  streamApplication,
  type Application,
  type CreateApplicationRequest,
} from "@/lib/api/applications";

const MESSAGE_TYPES = [
  { value: "email_detailed", label: "Detailed Email" },
  { value: "email_short", label: "Short Email" },
  { value: "linkedin_message", label: "LinkedIn Message" },
  { value: "linkedin_connection", label: "LinkedIn Connection" },
  { value: "linkedin_inmail", label: "LinkedIn InMail" },
  { value: "ycombinator", label: "Y Combinator" },
];

export default function GeneratePage() {
  const router = useRouter();
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [loadingResumes, setLoadingResumes] = useState(true);

  // Form state
  const [selectedResumeId, setSelectedResumeId] = useState<number | undefined>();
  const [jobDescription, setJobDescription] = useState("");
  const [messageType, setMessageType] = useState("email_detailed");
  const [recruiterName, setRecruiterName] = useState("");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [positionTitle, setPositionTitle] = useState("");
  const [jobUrl, setJobUrl] = useState("");

  // Result state
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<Application | null>(null);
  const [editedMessage, setEditedMessage] = useState("");

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

  async function handleGenerate() {
    if (!jobDescription.trim()) {
      toast.error("Paste a job description first");
      return;
    }
    setGenerating(true);
    setResult(null);
    setEditedMessage("");

    try {
      const payload: CreateApplicationRequest = {
        job_description: jobDescription,
        message_type: messageType,
        resume_id: selectedResumeId,
        recruiter_name: recruiterName || undefined,
        recipient_email: recipientEmail || undefined,
        position_title: positionTitle || undefined,
        job_url: jobUrl || undefined,
      };

      await streamApplication(
        payload,
        (text) => setEditedMessage((prev) => prev + text),
        (app) => {
          setResult(app);
          setGenerating(false);
          toast.success("Message generated");
        },
        (error) => {
          toast.error(error || "Failed to generate message");
          setGenerating(false);
        },
        async () => {
          const supabase = createClient();
          const { data: { session } } = await supabase.auth.getSession();
          return session?.access_token || null;
        },
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to generate message";
      toast.error(msg);
      setGenerating(false);
    }
  }

  function handleViewApplication() {
    if (result) router.push(`/applications/${result.id}`);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Generate Message</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Create a personalized application message
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left column — inputs */}
        <div className="space-y-4">
          {/* Resume selector */}
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">
              Resume
            </label>
            {loadingResumes ? (
              <div className="h-9 bg-muted rounded-md animate-pulse" />
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
                className="w-full h-9 px-3 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent"
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

          {/* Message type */}
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">
              Message Type
            </label>
            <div className="flex flex-wrap gap-1.5">
              {MESSAGE_TYPES.map((t) => (
                <button
                  key={t.value}
                  onClick={() => setMessageType(t.value)}
                  className={`px-3 py-1.5 text-xs rounded-md border transition-colors ${
                    messageType === t.value
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-border text-muted-foreground hover:text-foreground hover:border-muted-foreground"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          {/* Position + Recruiter */}
          <div className="grid grid-cols-2 gap-3">
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
          </div>

          {/* Recipient email + Job URL */}
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
                Job URL
              </label>
              <input
                value={jobUrl}
                onChange={(e) => setJobUrl(e.target.value)}
                placeholder="https://..."
                className="w-full h-9 px-3 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted-foreground/50"
              />
            </div>
          </div>

          {/* Job description */}
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

          {/* Generate button */}
          <button
            onClick={handleGenerate}
            disabled={generating || !jobDescription.trim()}
            className="w-full h-10 bg-accent text-accent-foreground text-sm font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {generating ? "Generating..." : "Generate Message"}
          </button>
        </div>

        {/* Right column — result */}
        <div>
          {generating ? (
            editedMessage ? (
              <div className="border border-accent/30 rounded-lg overflow-hidden">
                <div className="px-4 py-3 border-b border-border flex items-center gap-2">
                  <div className="h-2 w-2 bg-accent rounded-full animate-pulse" />
                  <p className="text-sm font-medium text-muted-foreground">
                    Generating...
                  </p>
                </div>
                <div className="px-4 py-3 text-sm font-mono leading-relaxed whitespace-pre-wrap min-h-[300px] max-h-[500px] overflow-y-auto">
                  {editedMessage}
                  <span className="inline-block w-2 h-4 bg-accent/70 animate-pulse ml-0.5 align-text-bottom" />
                </div>
              </div>
            ) : (
              <div className="border border-border rounded-lg p-6 space-y-3 animate-pulse">
                <div className="h-4 bg-muted rounded w-1/3" />
                <div className="h-3 bg-muted rounded w-full" />
                <div className="h-3 bg-muted rounded w-5/6" />
                <div className="h-3 bg-muted rounded w-4/6" />
                <div className="h-3 bg-muted rounded w-full" />
                <div className="h-3 bg-muted rounded w-3/4" />
              </div>
            )
          ) : result ? (
            <div className="border border-border rounded-lg overflow-hidden">
              <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">
                    {result.company_name || "Application"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {result.position_title || result.message_type}
                  </p>
                </div>
                <span className="text-[10px] font-medium px-2 py-0.5 bg-accent/10 text-accent rounded">
                  {result.status.replace("_", " ")}
                </span>
              </div>
              <textarea
                value={editedMessage}
                onChange={(e) => setEditedMessage(e.target.value)}
                rows={16}
                className="w-full px-4 py-3 text-sm bg-background border-none focus:outline-none resize-y font-mono leading-relaxed"
              />
              <div className="px-4 py-3 border-t border-border flex items-center gap-2">
                <button
                  onClick={handleViewApplication}
                  className="px-4 py-2 text-sm font-medium bg-accent text-accent-foreground rounded-md hover:opacity-90 transition-opacity"
                >
                  Review & Send
                </button>
                <button
                  onClick={() => {
                    setResult(null);
                    setEditedMessage("");
                  }}
                  className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
                >
                  Discard
                </button>
              </div>
            </div>
          ) : (
            <div className="border border-dashed border-border rounded-lg p-12 flex items-center justify-center h-full min-h-[300px]">
              <p className="text-sm text-muted-foreground text-center">
                Paste a job description and click Generate
                <br />
                <span className="text-xs opacity-60">
                  The AI will craft a personalized message using your resume
                </span>
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
