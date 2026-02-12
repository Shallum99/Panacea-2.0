"use client";

import {
  Briefcase,
  MapPin,
  Copy,
  Check,
  Download,
  ExternalLink,
  Mail,
  FileText,
  Zap,
  Star,
} from "lucide-react";
import { useState } from "react";
import { useRouter } from "next/navigation";

interface Props {
  richType: string;
  data: unknown;
}

export default function ChatRichResult({ richType, data }: Props) {
  switch (richType) {
    case "job_cards":
      return <JobCardGrid data={data} />;
    case "job_detail":
      return <JobDetail data={data} />;
    case "message_preview":
      return <MessagePreview data={data} />;
    case "resume_score":
      return <ResumeScoreCard data={data} />;
    case "resume_tailored":
      return <TailorResult data={data} />;
    case "applications_list":
      return <ApplicationsList data={data} />;
    case "email_sent":
      return <EmailConfirmation data={data} />;
    case "job_saved":
      return <JobSaved data={data} />;
    case "resumes_list":
      return <ResumesList data={data} />;
    case "error":
      return <ErrorResult data={data} />;
    default:
      return <GenericResult data={data} />;
  }
}

// ── Job Cards ────────────────────────────────────────────────────────

interface JobItem {
  title?: string;
  company?: string;
  location?: string;
  source?: string;
  url?: string;
  department?: string;
}

function JobCardGrid({ data }: { data: unknown }) {
  const d = data as { jobs?: JobItem[]; total?: number };
  const jobs = d.jobs || [];

  if (jobs.length === 0) {
    return (
      <div className="text-xs text-muted-foreground py-2">
        No jobs found matching your search.
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {jobs.slice(0, 8).map((job, i) => (
        <div
          key={i}
          className="flex items-center justify-between px-3 py-2 rounded-lg border border-border bg-card text-xs hover:border-accent/30 transition-colors"
        >
          <div className="min-w-0 flex-1">
            <p className="font-medium truncate">{job.title}</p>
            <div className="flex items-center gap-2 text-muted-foreground mt-0.5">
              <span className="flex items-center gap-1">
                <Briefcase size={10} />
                {job.company}
              </span>
              {job.location && (
                <span className="flex items-center gap-1">
                  <MapPin size={10} />
                  {job.location}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0 ml-2">
            <span className="px-1.5 py-0.5 rounded bg-muted text-[10px] text-muted-foreground">
              {job.source}
            </span>
            {job.url && (
              <a
                href={job.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-muted-foreground hover:text-foreground"
              >
                <ExternalLink size={12} />
              </a>
            )}
          </div>
        </div>
      ))}
      {(d.total || 0) > 8 && (
        <p className="text-[10px] text-muted-foreground text-center">
          +{(d.total || 0) - 8} more results
        </p>
      )}
    </div>
  );
}

// ── Job Detail ───────────────────────────────────────────────────────

function JobDetail({ data }: { data: unknown }) {
  const d = data as {
    title?: string;
    company?: string;
    location?: string;
    content?: string;
    url?: string;
  };

  return (
    <div className="rounded-lg border border-border bg-card p-3 text-xs space-y-2">
      <div>
        <p className="font-medium text-sm">{d.title}</p>
        <p className="text-muted-foreground">
          {d.company}
          {d.location ? ` - ${d.location}` : ""}
        </p>
      </div>
      {d.content && (
        <p className="text-muted-foreground line-clamp-4">{d.content}</p>
      )}
      {d.url && (
        <a
          href={d.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent hover:underline flex items-center gap-1"
        >
          <ExternalLink size={10} /> View listing
        </a>
      )}
    </div>
  );
}

// ── Message Preview ──────────────────────────────────────────────────

function MessagePreview({ data }: { data: unknown }) {
  const [copied, setCopied] = useState(false);
  const d = data as {
    message?: string;
    subject?: string;
    message_type?: string;
    application_id?: number;
    resume_used?: string;
  };

  async function handleCopy() {
    await navigator.clipboard.writeText(d.message || "");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="rounded-lg border border-border bg-card p-3 text-xs space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Mail size={12} className="text-accent" />
          <span className="font-medium">{d.subject}</span>
        </div>
        <button
          onClick={handleCopy}
          className="text-muted-foreground hover:text-foreground transition-colors"
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
        </button>
      </div>
      {d.message_type && (
        <span className="px-1.5 py-0.5 rounded bg-accent/10 text-accent text-[10px]">
          {d.message_type}
        </span>
      )}
      <div className="text-muted-foreground whitespace-pre-wrap max-h-40 overflow-y-auto leading-relaxed">
        {d.message}
      </div>
      {d.resume_used && (
        <p className="text-[10px] text-muted-foreground">
          Resume: {d.resume_used}
        </p>
      )}
    </div>
  );
}

// ── ATS Score ────────────────────────────────────────────────────────

function ResumeScoreCard({ data }: { data: unknown }) {
  const d = data as {
    score?: number;
    strengths?: string[];
    improvements?: string[];
    missing_keywords?: string[];
    resume_title?: string;
  };
  const score = d.score || 0;
  const color =
    score >= 80 ? "text-success" : score >= 60 ? "text-accent" : "text-destructive";

  return (
    <div className="rounded-lg border border-border bg-card p-3 text-xs space-y-2">
      <div className="flex items-center justify-between">
        <span className="font-medium flex items-center gap-1.5">
          <Star size={12} className="text-accent" />
          ATS Score {d.resume_title && `- ${d.resume_title}`}
        </span>
        <span className={`text-lg font-bold ${color}`}>{score}</span>
      </div>
      {d.strengths && d.strengths.length > 0 && (
        <div>
          <p className="font-medium text-success mb-0.5">Strengths</p>
          {d.strengths.map((s, i) => (
            <p key={i} className="text-muted-foreground">
              + {s}
            </p>
          ))}
        </div>
      )}
      {d.improvements && d.improvements.length > 0 && (
        <div>
          <p className="font-medium text-destructive mb-0.5">Improvements</p>
          {d.improvements.map((s, i) => (
            <p key={i} className="text-muted-foreground">
              - {s}
            </p>
          ))}
        </div>
      )}
      {d.missing_keywords && d.missing_keywords.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1">
          {d.missing_keywords.map((kw, i) => (
            <span
              key={i}
              className="px-1.5 py-0.5 rounded bg-destructive/10 text-destructive text-[10px]"
            >
              {kw}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Tailor Result ────────────────────────────────────────────────────

function TailorResult({ data }: { data: unknown }) {
  const d = data as {
    resume_title?: string;
    download_id?: string;
    sections_optimized?: string[];
    ats_score_before?: number;
    ats_score_after?: number;
  };

  return (
    <div className="rounded-lg border border-border bg-card p-3 text-xs space-y-2">
      <div className="flex items-center gap-1.5 font-medium">
        <FileText size={12} className="text-accent" />
        Resume Tailored: {d.resume_title}
      </div>
      {d.ats_score_before != null && d.ats_score_after != null && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">
            ATS: {d.ats_score_before}%
          </span>
          <span className="text-accent">→</span>
          <span className="text-success font-medium">
            {d.ats_score_after}%
          </span>
        </div>
      )}
      {d.sections_optimized && d.sections_optimized.length > 0 && (
        <p className="text-muted-foreground">
          Optimized: {d.sections_optimized.join(", ")}
        </p>
      )}
      {d.download_id && (
        <a
          href={`/api/resume-tailor/download/${d.download_id}`}
          className="flex items-center gap-1 text-accent hover:underline"
        >
          <Download size={10} /> Download tailored PDF
        </a>
      )}
    </div>
  );
}

// ── Applications List ────────────────────────────────────────────────

interface AppItem {
  id?: number;
  position_title?: string;
  company_name?: string;
  status?: string;
  sent_at?: string;
}

function ApplicationsList({ data }: { data: unknown }) {
  const d = data as { applications?: AppItem[]; total?: number };
  const apps = d.applications || [];

  const statusColor: Record<string, string> = {
    draft: "bg-muted text-muted-foreground",
    message_generated: "bg-accent/10 text-accent",
    sent: "bg-success/10 text-success",
    failed: "bg-destructive/10 text-destructive",
    replied: "bg-accent-secondary/10 text-accent-secondary",
  };

  return (
    <div className="space-y-1">
      {apps.slice(0, 10).map((app, i) => (
        <div
          key={i}
          className="flex items-center justify-between px-3 py-2 rounded-lg border border-border bg-card text-xs"
        >
          <div className="min-w-0">
            <p className="font-medium truncate">
              {app.position_title || "Untitled"}
            </p>
            <p className="text-muted-foreground">{app.company_name}</p>
          </div>
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] ${
              statusColor[app.status || ""] || "bg-muted text-muted-foreground"
            }`}
          >
            {app.status}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Email Sent ───────────────────────────────────────────────────────

function EmailConfirmation({ data }: { data: unknown }) {
  const d = data as {
    success?: boolean;
    recipient?: string;
    subject?: string;
    error?: string;
  };

  if (d.error) {
    return <ErrorResult data={d} />;
  }

  return (
    <div className="rounded-lg border border-success/30 bg-success/5 p-3 text-xs">
      <div className="flex items-center gap-2">
        <Check size={14} className="text-success" />
        <span className="font-medium text-success">Email Sent</span>
      </div>
      <p className="text-muted-foreground mt-1">To: {d.recipient}</p>
      <p className="text-muted-foreground">Subject: {d.subject}</p>
    </div>
  );
}

// ── Job Saved ────────────────────────────────────────────────────────

function JobSaved({ data }: { data: unknown }) {
  const router = useRouter();
  const d = data as {
    job_id?: number;
    title?: string;
    company?: string;
  };

  return (
    <div className="rounded-lg border border-border bg-card p-3 text-xs">
      <div className="flex items-center gap-2">
        <Check size={12} className="text-success" />
        <span className="font-medium">
          Saved: {d.title} {d.company ? `at ${d.company}` : ""}
        </span>
      </div>
      {d.job_id && (
        <button
          onClick={() => router.push(`/generate?job=${d.job_id}`)}
          className="mt-1.5 flex items-center gap-1 text-accent hover:underline"
        >
          <Zap size={10} /> Go to Generate
        </button>
      )}
    </div>
  );
}

// ── Resumes List ─────────────────────────────────────────────────────

function ResumesList({ data }: { data: unknown }) {
  const d = data as {
    resumes?: Array<{
      id: number;
      title: string;
      is_active: boolean;
      profile_type?: string;
      skills?: string[];
    }>;
  };
  const resumes = d.resumes || [];

  return (
    <div className="space-y-1">
      {resumes.map((r) => (
        <div
          key={r.id}
          className={`px-3 py-2 rounded-lg border text-xs ${
            r.is_active
              ? "border-accent/30 bg-accent/5"
              : "border-border bg-card"
          }`}
        >
          <div className="flex items-center gap-2">
            <FileText size={12} />
            <span className="font-medium">{r.title}</span>
            {r.is_active && (
              <span className="px-1 py-0.5 rounded bg-accent/10 text-accent text-[10px]">
                Active
              </span>
            )}
          </div>
          {r.profile_type && (
            <p className="text-muted-foreground mt-0.5">{r.profile_type}</p>
          )}
          {r.skills && r.skills.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {r.skills.slice(0, 5).map((s) => (
                <span
                  key={s}
                  className="px-1 py-0.5 rounded bg-muted text-[10px] text-muted-foreground"
                >
                  {s}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Error ────────────────────────────────────────────────────────────

function ErrorResult({ data }: { data: unknown }) {
  const d = data as { error?: string };
  return (
    <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
      {d.error || "An error occurred"}
    </div>
  );
}

// ── Generic fallback ─────────────────────────────────────────────────

function GenericResult({ data }: { data: unknown }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3 text-xs text-muted-foreground">
      <pre className="whitespace-pre-wrap max-h-32 overflow-y-auto">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
