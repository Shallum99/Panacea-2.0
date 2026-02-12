"use client";

import InlineMessagePreview from "./InlineMessagePreview";
import InlineResumeViewer from "./InlineResumeViewer";
import InlineATSScore from "./InlineATSScore";
import InlineEmailForm from "./InlineEmailForm";
import InlineJobCards from "./InlineJobCards";
import InlineJobDetail from "./InlineJobDetail";

interface Props {
  richType: string;
  data: unknown;
  onSendMessage?: (text: string) => void;
}

export default function InlineRichResult({
  richType,
  data,
  onSendMessage,
}: Props) {
  switch (richType) {
    case "message_preview":
      return (
        <InlineMessagePreview
          data={data as Record<string, unknown>}
          onSendMessage={onSendMessage}
        />
      );
    case "resume_tailored":
      return <InlineResumeViewer data={data as Record<string, unknown>} />;
    case "resume_score":
      return <InlineATSScore data={data as Record<string, unknown>} />;
    case "email_sent":
      return <InlineEmailForm data={data as Record<string, unknown>} />;
    case "job_cards":
      return <InlineJobCards data={data as Record<string, unknown>} />;
    case "job_detail":
      return <InlineJobDetail data={data as Record<string, unknown>} />;
    case "job_saved":
      return <JobSavedInline data={data as Record<string, unknown>} />;
    case "resumes_list":
      return <ResumesListInline data={data as Record<string, unknown>} />;
    case "applications_list":
      return (
        <ApplicationsListInline data={data as Record<string, unknown>} />
      );
    case "error":
      return <ErrorInline data={data as Record<string, unknown>} />;
    default:
      return <GenericInline data={data} />;
  }
}

// ── Small inline components for less common types ──

function JobSavedInline({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="ml-10 flex items-center gap-2 px-4 py-2.5 rounded-xl border border-success/20 bg-success/[0.03] text-[12px]">
      <span className="text-success font-medium">Saved</span>
      <span className="text-muted-foreground">
        {(data.title as string) || "Job"}
        {data.company ? ` at ${data.company}` : ""}
      </span>
    </div>
  );
}

function ResumesListInline({ data }: { data: Record<string, unknown> }) {
  const resumes = (data.resumes || []) as Array<{
    id: number;
    title: string;
    is_active: boolean;
    profile_type?: string;
  }>;
  return (
    <div className="ml-10 space-y-1">
      {resumes.map((r) => (
        <div
          key={r.id}
          className={`px-4 py-2 rounded-xl border text-[12px] ${
            r.is_active
              ? "border-accent/20 bg-accent/[0.03]"
              : "border-border bg-card/40"
          }`}
        >
          <span className="font-medium">{r.title}</span>
          {r.is_active && (
            <span className="ml-2 px-1.5 py-0.5 rounded-full bg-accent/10 text-accent text-[10px]">
              Active
            </span>
          )}
          {r.profile_type && (
            <span className="ml-2 text-muted-foreground">
              {r.profile_type}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

function ApplicationsListInline({ data }: { data: Record<string, unknown> }) {
  const apps = (data.applications || []) as Array<{
    id: number;
    position_title?: string;
    company_name?: string;
    status?: string;
  }>;
  const statusColors: Record<string, string> = {
    draft: "bg-muted text-muted-foreground",
    message_generated: "bg-accent/10 text-accent",
    sent: "bg-success/10 text-success",
    failed: "bg-destructive/10 text-destructive",
  };
  return (
    <div className="ml-10 space-y-1">
      {apps.slice(0, 10).map((a) => (
        <div
          key={a.id}
          className="flex items-center justify-between px-4 py-2 rounded-xl border border-border bg-card/40 text-[12px]"
        >
          <div className="min-w-0">
            <p className="font-medium truncate">
              {a.position_title || "Untitled"}
            </p>
            <p className="text-[11px] text-muted-foreground">
              {a.company_name}
            </p>
          </div>
          <span
            className={`shrink-0 px-2 py-0.5 rounded-full text-[10px] ${
              statusColors[a.status || ""] || "bg-muted text-muted-foreground"
            }`}
          >
            {a.status}
          </span>
        </div>
      ))}
    </div>
  );
}

function ErrorInline({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="ml-10 px-4 py-2.5 rounded-xl border border-destructive/20 bg-destructive/[0.03] text-[12px] text-destructive">
      {(data.error as string) || "An error occurred"}
    </div>
  );
}

function GenericInline({ data }: { data: unknown }) {
  return (
    <div className="ml-10 px-4 py-2.5 rounded-xl border border-border bg-card/40 text-[11px] text-muted-foreground">
      <pre className="whitespace-pre-wrap max-h-32 overflow-y-auto">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
