"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  Upload,
  Loader2,
  Link as LinkIcon,
  Mail,
  FileText,
  ChevronDown,
  Check,
  Plus,
} from "lucide-react";
import type { ChatContext } from "@/lib/api/chat";
import {
  extractJdFields,
  uploadJdPdf,
  type JdExtractedFields,
} from "@/lib/api/applications";
import { uploadResume } from "@/lib/api/resumes";
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
  onResumesChanged?: () => void;
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
  onResumesChanged,
}: Props) {
  // ── Field state ──
  const [jd, setJd] = useState(context.job_description || "");
  const [jobUrl, setJobUrl] = useState(context.job_url || "");
  const [resumeId, setResumeId] = useState<number | undefined>(
    context.resume_id
  );
  const [selectedMessageTypes, setSelectedMessageTypes] = useState<Set<string>>(
    new Set([context.message_type || "email_detailed"])
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

  // ── Action selection state ──
  const [selectedActions, setSelectedActions] = useState<Set<"generate" | "tailor">>(
    new Set(["generate", "tailor"])
  );

  // ── Extraction state ──
  const [fetchingUrl, setFetchingUrl] = useState(false);
  const [uploadingPdf, setUploadingPdf] = useState(false);
  const [uploadingResume, setUploadingResume] = useState(false);
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

  // ── JD PDF upload ──
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

  // ── Resume upload ──
  async function handleResumeUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingResume(true);
    try {
      const title = file.name.replace(/\.pdf$/i, "");
      const newResume = await uploadResume(file, title, true);
      setResumeId(newResume.id);
      onResumesChanged?.();
    } catch {
      // silent
    } finally {
      setUploadingResume(false);
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

  // ── Toggle helpers ──
  function toggleMessageType(value: string) {
    setSelectedMessageTypes((prev) => {
      const next = new Set(prev);
      if (next.has(value)) {
        if (next.size > 1) next.delete(value);
      } else {
        next.add(value);
      }
      return next;
    });
  }

  function toggleAction(action: "generate" | "tailor") {
    setSelectedActions((prev) => {
      const next = new Set(prev);
      if (next.has(action)) {
        next.delete(action);
      } else {
        next.add(action);
      }
      return next;
    });
  }

  // ── Go handler — builds compound prompt ──
  function handleGo() {
    const ctx: ChatContext = {
      job_description: jd || undefined,
      job_url: jobUrl || undefined,
      resume_id: resumeId,
      message_type: Array.from(selectedMessageTypes)[0],
      position_title: positionTitle || undefined,
      recruiter_name: recruiterName || undefined,
      recipient_email: recipientEmail || undefined,
    };
    onSetContext(ctx);

    const parts: string[] = [];

    if (selectedActions.has("generate")) {
      const types = Array.from(selectedMessageTypes);
      const labels = types.map(
        (t) => MESSAGE_TYPES.find((mt) => mt.value === t)?.label?.toLowerCase() || t
      );
      if (labels.length === 1) {
        parts.push(`generate a ${labels[0]}`);
      } else {
        const last = labels.pop();
        parts.push(`generate a ${labels.join(", a ")} and a ${last}`);
      }
    }

    if (selectedActions.has("tailor")) {
      parts.push("tailor my resume to match this job description");
    }

    const prompt = parts.join(", and ") + " for this role";
    if (parts.length > 0) sendMessage(prompt);
  }

  const hasJd = !!jd.trim();
  const canGo =
    hasJd &&
    selectedActions.size > 0 &&
    (!selectedActions.has("tailor") || !!resumeId);

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
            <div className="flex gap-2">
              <div className="relative flex-1">
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
              <label
                className={`shrink-0 w-10 h-[38px] rounded-lg border flex items-center justify-center cursor-pointer transition-colors ${
                  uploadingResume
                    ? "border-[#333] bg-[#111]"
                    : "border-[#1a1a1a] bg-[#0a0a0a] hover:border-[#333]"
                }`}
                title="Upload new resume"
              >
                {uploadingResume ? (
                  <Loader2 size={14} className="animate-spin text-[#555]" />
                ) : (
                  <Plus size={14} className="text-[#666]" />
                )}
                <input
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={handleResumeUpload}
                  disabled={uploadingResume}
                />
              </label>
            </div>
          </div>
        </div>

        {/* ── Message Type (multi-select) ── */}
        <div>
          <label className="block text-[12px] font-medium text-[#777] uppercase tracking-[0.05em] mb-2">
            Message Type
            {selectedMessageTypes.size > 1 && (
              <span className="ml-1.5 text-[10px] text-[#555] font-normal normal-case tracking-normal">
                {selectedMessageTypes.size} selected
              </span>
            )}
          </label>
          <div className="flex flex-wrap gap-1.5">
            {MESSAGE_TYPES.map((mt) => (
              <button
                key={mt.value}
                onClick={() => toggleMessageType(mt.value)}
                className={`px-3 py-1.5 rounded-md text-[12px] font-medium transition-all duration-150 ${
                  selectedMessageTypes.has(mt.value)
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

        {/* ── Action Selection (checkboxes) ── */}
        <div>
          <label className="block text-[12px] font-medium text-[#777] uppercase tracking-[0.05em] mb-2">
            Actions
          </label>
          <div className="flex gap-3">
            {/* Generate Message */}
            <button
              onClick={() => toggleAction("generate")}
              disabled={!hasJd}
              className={`flex-1 flex items-center gap-3 p-4 rounded-xl border transition-all duration-150 text-left ${
                selectedActions.has("generate")
                  ? "border-[#333] bg-[#111]"
                  : "border-[#1a1a1a] bg-[#0a0a0a] hover:border-[#2a2a2a]"
              } ${!hasJd ? "opacity-30 cursor-not-allowed" : ""}`}
            >
              <div
                className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors ${
                  selectedActions.has("generate")
                    ? "bg-[#ededed] border-[#ededed]"
                    : "border-[#444]"
                }`}
              >
                {selectedActions.has("generate") && (
                  <Check size={10} className="text-black" />
                )}
              </div>
              <div className="flex items-center gap-2">
                <Mail size={14} className="text-[#888] shrink-0" />
                <span className="text-[13px] font-medium text-[#ededed]">
                  Generate Message
                </span>
              </div>
            </button>

            {/* Tailor Resume */}
            <button
              onClick={() => toggleAction("tailor")}
              disabled={!hasJd || !resumeId}
              className={`flex-1 flex items-center gap-3 p-4 rounded-xl border transition-all duration-150 text-left ${
                selectedActions.has("tailor")
                  ? "border-[#333] bg-[#111]"
                  : "border-[#1a1a1a] bg-[#0a0a0a] hover:border-[#2a2a2a]"
              } ${!hasJd || !resumeId ? "opacity-30 cursor-not-allowed" : ""}`}
            >
              <div
                className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors ${
                  selectedActions.has("tailor")
                    ? "bg-[#ededed] border-[#ededed]"
                    : "border-[#444]"
                }`}
              >
                {selectedActions.has("tailor") && (
                  <Check size={10} className="text-black" />
                )}
              </div>
              <div className="flex items-center gap-2">
                <FileText size={14} className="text-[#888] shrink-0" />
                <span className="text-[13px] font-medium text-[#ededed]">
                  Tailor Resume
                </span>
              </div>
            </button>
          </div>
        </div>

        {/* ── Go Button ── */}
        <button
          onClick={handleGo}
          disabled={!canGo || sending}
          className="w-full py-3 rounded-xl bg-[#ededed] text-black text-[14px] font-semibold hover:bg-white transition-all duration-150 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-[#ededed]"
        >
          {sending ? (
            <Loader2 size={16} className="animate-spin mx-auto" />
          ) : (
            "Go"
          )}
        </button>
      </div>
    </div>
  );
}
