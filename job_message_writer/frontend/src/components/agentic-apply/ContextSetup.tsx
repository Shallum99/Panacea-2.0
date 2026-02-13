"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  Upload,
  Loader2,
  Link as LinkIcon,
  Mail,
  FileText,
  ChevronDown,
} from "lucide-react";
import type { ChatContext } from "@/lib/api/chat";
import {
  extractJdFields,
  uploadJdPdf,
  type JdExtractedFields,
} from "@/lib/api/applications";
import api from "@/lib/api";

interface ResumeOption {
  id: number;
  title: string;
  is_active: boolean;
}

interface Props {
  context: ChatContext;
  onSetContext: (ctx: ChatContext) => void;
  resumes: ResumeOption[];
  sendMessage: (text?: string) => void;
  sending: boolean;
}

const MESSAGE_TYPES = [
  { value: "email_detailed", label: "Detailed Email" },
  { value: "email_short", label: "Short Email" },
  { value: "linkedin_message", label: "LinkedIn" },
  { value: "linkedin_connection", label: "Connection" },
  { value: "linkedin_inmail", label: "InMail" },
  { value: "ycombinator", label: "YC" },
];

export default function ContextSetup({
  context,
  onSetContext,
  resumes,
  sendMessage,
  sending,
}: Props) {
  // ── Field state ──
  const [jd, setJd] = useState(context.job_description || "");
  const [jobUrl, setJobUrl] = useState(context.job_url || "");
  const [resumeId, setResumeId] = useState<number | undefined>(
    context.resume_id
  );
  const [messageType, setMessageType] = useState(
    context.message_type || "email_detailed"
  );
  const [positionTitle, setPositionTitle] = useState(
    context.position_title || ""
  );
  const [recruiterName, setRecruiterName] = useState(
    context.recruiter_name || ""
  );
  const [recipientEmail, setRecipientEmail] = useState(
    context.recipient_email || ""
  );
  const [showDetails, setShowDetails] = useState(
    !!(context.position_title || context.recruiter_name || context.recipient_email)
  );

  // ── Extraction state ──
  const [fetchingUrl, setFetchingUrl] = useState(false);
  const [uploadingPdf, setUploadingPdf] = useState(false);
  const [analyzingJd, setAnalyzingJd] = useState(false);
  const [jdFields, setJdFields] = useState<JdExtractedFields | null>(null);

  // ── Refs ──
  const analyzeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastAnalyzedRef = useRef("");
  const userEditedRef = useRef<Set<string>>(new Set());

  // ── Default to active resume ──
  useEffect(() => {
    if (!resumeId && resumes.length > 0) {
      const active = resumes.find((r) => r.is_active);
      if (active) setResumeId(active.id);
    }
  }, [resumes, resumeId]);

  // ── JD Analysis (debounced) ──
  const analyzeJd = useCallback(async (text: string) => {
    if (text.trim().length < 100 || text === lastAnalyzedRef.current) return;
    lastAnalyzedRef.current = text;
    setAnalyzingJd(true);
    try {
      const fields = await extractJdFields(text);
      setJdFields(fields);
      if (fields.position_title && !userEditedRef.current.has("positionTitle"))
        setPositionTitle(fields.position_title);
      if (fields.recruiter_name && !userEditedRef.current.has("recruiterName"))
        setRecruiterName(fields.recruiter_name);
      if (
        fields.recipient_email &&
        !userEditedRef.current.has("recipientEmail")
      )
        setRecipientEmail(fields.recipient_email);
      // Auto-show details section if we extracted anything
      if (fields.position_title || fields.recruiter_name || fields.recipient_email) {
        setShowDetails(true);
      }
    } catch {
      // silent
    } finally {
      setAnalyzingJd(false);
    }
  }, []);

  useEffect(() => {
    if (analyzeTimerRef.current) clearTimeout(analyzeTimerRef.current);
    if (jd.trim().length >= 100) {
      analyzeTimerRef.current = setTimeout(() => analyzeJd(jd), 1200);
    }
    return () => {
      if (analyzeTimerRef.current) clearTimeout(analyzeTimerRef.current);
    };
  }, [jd, analyzeJd]);

  // ── URL fetch ──
  async function handleJobUrlChange(newUrl: string) {
    setJobUrl(newUrl);
    if (!newUrl.match(/^https?:\/\/.+\..+/)) return;
    if (jd.trim().length > 50) return;
    setFetchingUrl(true);
    try {
      const { data } = await api.post("/job-descriptions/from-url", {
        url: newUrl,
      });
      setJd(data.content || "");
      if (data.title && !userEditedRef.current.has("positionTitle"))
        setPositionTitle(data.title);
      if (data.company_info) {
        const info =
          typeof data.company_info === "string"
            ? JSON.parse(data.company_info)
            : data.company_info;
        if (info.recruiter_name && !userEditedRef.current.has("recruiterName"))
          setRecruiterName(info.recruiter_name);
        if (
          info.recipient_email &&
          !userEditedRef.current.has("recipientEmail")
        )
          setRecipientEmail(info.recipient_email);
        if (info.position_title && !userEditedRef.current.has("positionTitle"))
          setPositionTitle(info.position_title);
      }
    } catch {
      // silent
    } finally {
      setFetchingUrl(false);
    }
  }

  // ── JD textarea change (detects URL paste) ──
  function handleJdChange(val: string) {
    if (val.match(/^https?:\/\/\S+$/) && val.trim() === val && !jd) {
      setJd("");
      handleJobUrlChange(val.trim());
      return;
    }
    setJd(val);
  }

  // ── PDF upload ──
  async function handlePdfUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingPdf(true);
    try {
      const { text } = await uploadJdPdf(file);
      setJd(text);
    } catch {
      // silent
    } finally {
      setUploadingPdf(false);
      e.target.value = "";
    }
  }

  // ── Auto-fill check ──
  function isAutoFilled(field: string, value: string): boolean {
    if (!jdFields || userEditedRef.current.has(field) || !value) return false;
    const key =
      field === "positionTitle"
        ? "position_title"
        : field === "recruiterName"
          ? "recruiter_name"
          : "recipient_email";
    return jdFields[key as keyof JdExtractedFields] === value;
  }

  // ── Action handler ──
  function handleAction(action: "generate" | "tailor") {
    const ctx: ChatContext = {
      job_description: jd || undefined,
      job_url: jobUrl || undefined,
      resume_id: resumeId,
      message_type: messageType,
      position_title: positionTitle || undefined,
      recruiter_name: recruiterName || undefined,
      recipient_email: recipientEmail || undefined,
    };
    onSetContext(ctx);

    if (action === "generate") {
      const typeLabel =
        MESSAGE_TYPES.find((t) => t.value === messageType)?.label || "message";
      sendMessage(`Generate a ${typeLabel.toLowerCase()} for this role`);
    } else {
      sendMessage("Tailor my resume to match this job description");
    }
  }

  const canGenerate = !!jd.trim();
  const canTailor = !!jd.trim() && !!resumeId;

  return (
    <div className="w-full max-w-xl px-6 py-10">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-[22px] font-semibold text-[#ededed] tracking-[-0.02em]">
          New Application
        </h1>
        <p className="text-[13px] text-[#555] mt-1.5">
          Paste a job description, choose your resume, and go.
        </p>
      </div>

      <div className="space-y-5">
        {/* ── Job Description ── */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-[12px] font-medium text-[#777] uppercase tracking-[0.05em]">
              Job Description
            </label>
            <div className="flex items-center gap-3">
              {analyzingJd && (
                <span className="flex items-center gap-1.5 text-[11px] text-[#50e3c2]">
                  <Loader2 size={10} className="animate-spin" />
                  Analyzing
                </span>
              )}
              <label
                className={`flex items-center gap-1 text-[11px] cursor-pointer transition-colors ${
                  uploadingPdf
                    ? "text-[#555]"
                    : "text-[#666] hover:text-[#ededed]"
                }`}
              >
                <Upload size={11} />
                {uploadingPdf ? "Extracting..." : "Upload PDF"}
                <input
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={handlePdfUpload}
                  disabled={uploadingPdf}
                />
              </label>
            </div>
          </div>
          <textarea
            value={jd}
            onChange={(e) => handleJdChange(e.target.value)}
            placeholder="Paste a job URL or the full job description..."
            rows={5}
            className="w-full px-3.5 py-3 rounded-lg bg-[#0a0a0a] border border-[#1a1a1a] text-[13px] text-[#ededed] placeholder:text-[#333] focus:outline-none focus:border-[#333] resize-none transition-colors leading-relaxed"
          />
        </div>

        {/* ── URL + Resume ── */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[12px] font-medium text-[#777] uppercase tracking-[0.05em] mb-2 flex items-center gap-1.5">
              <LinkIcon size={10} />
              Job URL
              {fetchingUrl && (
                <span className="text-[10px] text-[#50e3c2] font-normal normal-case tracking-normal flex items-center gap-1">
                  <Loader2 size={9} className="animate-spin" />
                  extracting
                </span>
              )}
            </label>
            <input
              type="text"
              value={jobUrl}
              onChange={(e) => handleJobUrlChange(e.target.value)}
              placeholder="https://..."
              className={`w-full px-3.5 py-2.5 rounded-lg bg-[#0a0a0a] border text-[13px] text-[#ededed] placeholder:text-[#333] focus:outline-none transition-colors ${
                fetchingUrl
                  ? "border-[#333]"
                  : "border-[#1a1a1a] focus:border-[#333]"
              }`}
            />
          </div>
          <div>
            <label className="block text-[12px] font-medium text-[#777] uppercase tracking-[0.05em] mb-2">
              Resume
            </label>
            <div className="relative">
              <select
                value={resumeId ?? ""}
                onChange={(e) =>
                  setResumeId(
                    e.target.value ? Number(e.target.value) : undefined
                  )
                }
                className="w-full px-3.5 py-2.5 rounded-lg bg-[#0a0a0a] border border-[#1a1a1a] text-[13px] text-[#ededed] focus:outline-none focus:border-[#333] transition-colors appearance-none pr-8"
              >
                <option value="">Select resume...</option>
                {resumes.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.title}
                    {r.is_active ? " (Active)" : ""}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={12}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[#555] pointer-events-none"
              />
            </div>
          </div>
        </div>

        {/* ── Message Type ── */}
        <div>
          <label className="block text-[12px] font-medium text-[#777] uppercase tracking-[0.05em] mb-2">
            Message Type
          </label>
          <div className="flex flex-wrap gap-1.5">
            {MESSAGE_TYPES.map((mt) => (
              <button
                key={mt.value}
                onClick={() => setMessageType(mt.value)}
                className={`px-3 py-1.5 rounded-md text-[12px] font-medium transition-all duration-150 ${
                  messageType === mt.value
                    ? "bg-[#ededed] text-[#0a0a0a] shadow-[0_0_12px_rgba(237,237,237,0.08)]"
                    : "bg-[#0a0a0a] text-[#666] border border-[#1a1a1a] hover:border-[#333] hover:text-[#999]"
                }`}
              >
                {mt.label}
              </button>
            ))}
          </div>
        </div>

        {/* ── Optional Details (collapsible) ── */}
        <div>
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="flex items-center gap-1.5 text-[12px] text-[#555] hover:text-[#888] transition-colors"
          >
            <ChevronDown
              size={12}
              className={`transition-transform duration-200 ${showDetails ? "rotate-0" : "-rotate-90"}`}
            />
            Details
            {(positionTitle || recruiterName || recipientEmail) && (
              <span className="w-1.5 h-1.5 rounded-full bg-[#50e3c2]" />
            )}
          </button>

          {showDetails && (
            <div className="grid grid-cols-3 gap-3 mt-3">
              <div>
                <label className="block text-[11px] font-medium text-[#666] mb-1.5">
                  Position
                  {isAutoFilled("positionTitle", positionTitle) && (
                    <span className="ml-1 text-[9px] text-[#50e3c2] font-normal">
                      auto
                    </span>
                  )}
                </label>
                <input
                  type="text"
                  value={positionTitle}
                  onChange={(e) => {
                    userEditedRef.current.add("positionTitle");
                    setPositionTitle(e.target.value);
                  }}
                  placeholder="Senior Engineer"
                  className="w-full px-3 py-2 rounded-lg bg-[#0a0a0a] border border-[#1a1a1a] text-[12px] text-[#ededed] placeholder:text-[#333] focus:outline-none focus:border-[#333] transition-colors"
                />
              </div>
              <div>
                <label className="block text-[11px] font-medium text-[#666] mb-1.5">
                  Recruiter
                  {isAutoFilled("recruiterName", recruiterName) && (
                    <span className="ml-1 text-[9px] text-[#50e3c2] font-normal">
                      auto
                    </span>
                  )}
                </label>
                <input
                  type="text"
                  value={recruiterName}
                  onChange={(e) => {
                    userEditedRef.current.add("recruiterName");
                    setRecruiterName(e.target.value);
                  }}
                  placeholder="Optional"
                  className="w-full px-3 py-2 rounded-lg bg-[#0a0a0a] border border-[#1a1a1a] text-[12px] text-[#ededed] placeholder:text-[#333] focus:outline-none focus:border-[#333] transition-colors"
                />
              </div>
              <div>
                <label className="block text-[11px] font-medium text-[#666] mb-1.5">
                  Email
                  {isAutoFilled("recipientEmail", recipientEmail) && (
                    <span className="ml-1 text-[9px] text-[#50e3c2] font-normal">
                      auto
                    </span>
                  )}
                </label>
                <input
                  type="email"
                  value={recipientEmail}
                  onChange={(e) => {
                    userEditedRef.current.add("recipientEmail");
                    setRecipientEmail(e.target.value);
                  }}
                  placeholder="recruiter@co.com"
                  className="w-full px-3 py-2 rounded-lg bg-[#0a0a0a] border border-[#1a1a1a] text-[12px] text-[#ededed] placeholder:text-[#333] focus:outline-none focus:border-[#333] transition-colors"
                />
              </div>
            </div>
          )}
        </div>

        {/* ── Divider ── */}
        <div className="border-t border-[#111] my-1" />

        {/* ── Action Cards ── */}
        <div className="grid grid-cols-2 gap-3">
          {/* Generate Message */}
          <button
            onClick={() => handleAction("generate")}
            disabled={!canGenerate || sending}
            className="group relative p-5 rounded-xl border border-[#1a1a1a] bg-[#0a0a0a] text-left transition-all duration-200 hover:border-[#2a2a2a] hover:shadow-[0_0_30px_rgba(80,227,194,0.04)] disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:border-[#1a1a1a] disabled:hover:shadow-none"
          >
            <div className="w-9 h-9 rounded-lg bg-[#111] border border-[#1a1a1a] flex items-center justify-center mb-3.5 group-hover:border-[#333] transition-colors">
              <Mail size={16} className="text-[#ededed]" />
            </div>
            <h3 className="text-[14px] font-semibold text-[#ededed] mb-1">
              Generate Message
            </h3>
            <p className="text-[11px] text-[#555] leading-relaxed">
              Create a tailored message for this role
            </p>
            {sending && canGenerate && (
              <div className="absolute top-4 right-4">
                <Loader2 size={14} className="animate-spin text-[#555]" />
              </div>
            )}
          </button>

          {/* Tailor Resume */}
          <button
            onClick={() => handleAction("tailor")}
            disabled={!canTailor || sending}
            className="group relative p-5 rounded-xl border border-[#1a1a1a] bg-[#0a0a0a] text-left transition-all duration-200 hover:border-[#2a2a2a] hover:shadow-[0_0_30px_rgba(80,227,194,0.04)] disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:border-[#1a1a1a] disabled:hover:shadow-none"
          >
            <div className="w-9 h-9 rounded-lg bg-[#111] border border-[#1a1a1a] flex items-center justify-center mb-3.5 group-hover:border-[#333] transition-colors">
              <FileText size={16} className="text-[#ededed]" />
            </div>
            <h3 className="text-[14px] font-semibold text-[#ededed] mb-1">
              Tailor Resume
            </h3>
            <p className="text-[11px] text-[#555] leading-relaxed">
              Optimize your resume to match this JD
            </p>
            {!resumeId && jd.trim() && (
              <p className="text-[10px] text-[#444] mt-2">
                Select a resume first
              </p>
            )}
            {sending && canTailor && (
              <div className="absolute top-4 right-4">
                <Loader2 size={14} className="animate-spin text-[#555]" />
              </div>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
