"use client";

import InlineMessagePreview from "./InlineMessagePreview";
import InlineResumeViewer from "./InlineResumeViewer";
import InlineATSScore from "./InlineATSScore";
import InlineEmailForm from "./InlineEmailForm";
import InlineJobCards from "./InlineJobCards";
import InlineJobDetail from "./InlineJobDetail";
import ArtifactCard from "./ArtifactCard";

const ARTIFACT_TYPES = new Set(["message_preview", "resume_tailored", "resume_score"]);

interface Props {
  richType: string;
  data: unknown;
  onSendMessage?: (text: string) => void;
  onOpenArtifact?: (messageId: string) => void;
  activeArtifactMessageId?: string | null;
  messageId?: string;
}

function getArtifactTitle(richType: string, data: Record<string, unknown>): string {
  switch (richType) {
    case "message_preview":
      return (data.subject as string) || "Generated Message";
    case "resume_tailored": {
      const name = (data.resume_title as string) || "Resume";
      return `${name}`;
    }
    case "resume_score":
      return `ATS Score${data.resume_title ? ` \u2014 ${data.resume_title}` : ""}`;
    default:
      return "Artifact";
  }
}

function getArtifactSubtitle(richType: string, data: Record<string, unknown>): string | undefined {
  switch (richType) {
    case "message_preview":
      return data.message_type as string | undefined;
    case "resume_tailored": {
      const before = data.ats_score_before as number | undefined;
      const after = data.ats_score_after as number | undefined;
      if (before != null && after != null) return `ATS: ${before}% \u2192 ${after}%`;
      return undefined;
    }
    case "resume_score":
      return data.score != null ? `Score: ${data.score}` : undefined;
    default:
      return undefined;
  }
}

export default function InlineRichResult({
  richType,
  data,
  onSendMessage,
  onOpenArtifact,
  activeArtifactMessageId,
  messageId,
}: Props) {
  // Route artifact types to compact cards when artifact handler is available
  if (
    onOpenArtifact &&
    messageId &&
    ARTIFACT_TYPES.has(richType)
  ) {
    const d = data as Record<string, unknown>;
    return (
      <div className="space-y-2">
        <ArtifactCard
          type={richType as "message_preview" | "resume_tailored" | "resume_score"}
          title={getArtifactTitle(richType, d)}
          subtitle={getArtifactSubtitle(richType, d)}
          isActive={activeArtifactMessageId === messageId}
          onClick={() => onOpenArtifact(messageId)}
        />
        {richType === "resume_tailored" && onSendMessage && (
          <QuickEditChips onSendMessage={onSendMessage} />
        )}
      </div>
    );
  }

  // Full inline rendering (fallback or non-artifact types)
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
    case "company_research":
      return <CompanyResearchInline data={data as Record<string, unknown>} />;
    case "context_update":
      return <ContextUpdateInline data={data as Record<string, unknown>} />;
    case "error":
      return <ErrorInline data={data as Record<string, unknown>} />;
    default:
      return <GenericInline data={data} />;
  }
}

// ── Small inline components ──

function JobSavedInline({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-[#222] bg-[#0a0a0a] text-[12px]">
      <span className="text-[#50e3c2] font-medium">Saved</span>
      <span className="text-[#888]">
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
    <div className="space-y-1">
      {resumes.map((r) => (
        <div
          key={r.id}
          className={`px-4 py-2 rounded-lg border text-[12px] ${
            r.is_active
              ? "border-[#333] bg-[#0a0a0a]"
              : "border-[#222] bg-[#0a0a0a]"
          }`}
        >
          <span className="font-medium text-[#ededed]">{r.title}</span>
          {r.is_active && (
            <span className="ml-2 px-1.5 py-0.5 rounded bg-[#1a1a1a] text-[#888] text-[10px]">
              Active
            </span>
          )}
          {r.profile_type && (
            <span className="ml-2 text-[#666]">{r.profile_type}</span>
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
  return (
    <div className="space-y-1">
      {apps.slice(0, 10).map((a) => (
        <div
          key={a.id}
          className="flex items-center justify-between px-4 py-2 rounded-lg border border-[#222] bg-[#0a0a0a] text-[12px]"
        >
          <div className="min-w-0">
            <p className="font-medium text-[#ededed] truncate">
              {a.position_title || "Untitled"}
            </p>
            <p className="text-[11px] text-[#666]">{a.company_name}</p>
          </div>
          <span className="shrink-0 px-2 py-0.5 rounded bg-[#1a1a1a] text-[10px] text-[#888]">
            {a.status}
          </span>
        </div>
      ))}
    </div>
  );
}

function ErrorInline({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="px-4 py-2.5 rounded-lg border border-[#222] bg-[#0a0a0a] text-[12px] text-[#ee0000]">
      {(data.error as string) || "An error occurred"}
    </div>
  );
}

function ContextUpdateInline({ data }: { data: Record<string, unknown> }) {
  const fields: Array<{ label: string; value: string }> = [];
  if (data.position_title) fields.push({ label: "Role", value: data.position_title as string });
  if (data.company_name) fields.push({ label: "Company", value: data.company_name as string });
  if (data.recruiter_name) fields.push({ label: "Contact", value: data.recruiter_name as string });
  if (data.recipient_email) fields.push({ label: "Email", value: data.recipient_email as string });
  if (data.job_url) fields.push({ label: "URL", value: "Saved" });
  const hasJd = !!data.job_description;

  return (
    <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-[#222] bg-[#0a0a0a] text-[12px] flex-wrap">
      <span className="text-[#50e3c2] font-medium shrink-0">Context saved</span>
      {hasJd && (
        <span className="px-2 py-0.5 rounded bg-[#1a1a1a] text-[#888] text-[10px]">JD</span>
      )}
      {fields.map((f) => (
        <span key={f.label} className="px-2 py-0.5 rounded bg-[#1a1a1a] text-[#888] text-[10px]">
          {f.label}: {f.value}
        </span>
      ))}
    </div>
  );
}

function CompanyResearchInline({ data }: { data: Record<string, unknown> }) {
  const name = (data.company_name as string) || "Company";
  const summary = data.summary as string | undefined;
  const products = (data.products || []) as string[];
  const values = (data.culture_values || []) as string[];
  const facts = (data.notable_facts || []) as string[];
  const industry = data.industry as string | undefined;
  const size = data.size as string | undefined;
  const error = data.error as string | undefined;

  if (error) {
    return (
      <div className="px-4 py-2.5 rounded-lg border border-[#222] bg-[#0a0a0a] text-[12px] text-[#888]">
        <span className="text-[#666]">{error}</span>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-[#222] bg-[#0a0a0a] overflow-hidden">
      <div className="px-4 py-2.5 border-b border-[#1a1a1a] flex items-center gap-2">
        <span className="text-[13px] font-medium text-[#ededed]">{name}</span>
        {industry && (
          <span className="px-2 py-0.5 rounded bg-[#1a1a1a] text-[10px] text-[#666]">
            {industry}
          </span>
        )}
        {size && (
          <span className="px-2 py-0.5 rounded bg-[#1a1a1a] text-[10px] text-[#666]">
            {size}
          </span>
        )}
      </div>
      <div className="px-4 py-2.5 space-y-2 text-[12px]">
        {summary && <p className="text-[#999] leading-relaxed">{summary}</p>}
        {products.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            <span className="text-[10px] text-[#555] mr-1">Products:</span>
            {products.slice(0, 5).map((p) => (
              <span key={p} className="px-2 py-0.5 rounded bg-[#1a1a1a] text-[#888] text-[10px]">
                {p}
              </span>
            ))}
          </div>
        )}
        {values.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            <span className="text-[10px] text-[#555] mr-1">Values:</span>
            {values.slice(0, 5).map((v) => (
              <span key={v} className="px-2 py-0.5 rounded bg-[#1a1a1a] text-[#888] text-[10px]">
                {v}
              </span>
            ))}
          </div>
        )}
        {facts.length > 0 && (
          <ul className="text-[11px] text-[#777] space-y-0.5 list-disc list-inside">
            {facts.slice(0, 3).map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function GenericInline({ data }: { data: unknown }) {
  return (
    <div className="px-4 py-2.5 rounded-lg border border-[#222] bg-[#0a0a0a] text-[11px] text-[#888]">
      <pre className="whitespace-pre-wrap max-h-32 overflow-y-auto">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}

const QUICK_EDITS = [
  { label: "More technical", prompt: "Make the bullet points more technical with specific technologies and methodologies" },
  { label: "Add metrics", prompt: "Add quantifiable metrics and numbers to the bullet points where possible" },
  { label: "Shorten bullets", prompt: "Make the bullet points more concise — each should be one line" },
  { label: "Emphasize leadership", prompt: "Emphasize leadership, ownership, and cross-team collaboration in the bullet points" },
];

function QuickEditChips({ onSendMessage }: { onSendMessage: (text: string) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5 pl-1">
      {QUICK_EDITS.map((edit) => (
        <button
          key={edit.label}
          onClick={() => onSendMessage(edit.prompt)}
          className="px-2.5 py-1 rounded-md border border-[#222] bg-[#0a0a0a] text-[11px] text-[#888] hover:text-[#ededed] hover:border-[#444] transition-colors"
        >
          {edit.label}
        </button>
      ))}
    </div>
  );
}
