"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { X, Upload, Loader2, Link as LinkIcon } from "lucide-react";
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
  open: boolean;
  onClose: () => void;
  onSave: (ctx: ChatContext) => void;
  initialValues: ChatContext;
  resumes: ResumeOption[];
}

const MESSAGE_TYPES = [
  { value: "email_detailed", label: "Detailed Email" },
  { value: "email_short", label: "Short Email" },
  { value: "linkedin_message", label: "LinkedIn Message" },
  { value: "linkedin_connection", label: "LinkedIn Connection" },
  { value: "linkedin_inmail", label: "LinkedIn InMail" },
  { value: "ycombinator", label: "Y Combinator" },
];

export default function ContextModal({
  open,
  onClose,
  onSave,
  initialValues,
  resumes,
}: Props) {
  const [jd, setJd] = useState(initialValues.job_description || "");
  const [jobUrl, setJobUrl] = useState(initialValues.job_url || "");
  const [resumeId, setResumeId] = useState<number | undefined>(
    initialValues.resume_id
  );
  const [messageType, setMessageType] = useState(
    initialValues.message_type || "email_detailed"
  );
  const [positionTitle, setPositionTitle] = useState(
    initialValues.position_title || ""
  );
  const [recruiterName, setRecruiterName] = useState(
    initialValues.recruiter_name || ""
  );
  const [recipientEmail, setRecipientEmail] = useState(
    initialValues.recipient_email || ""
  );

  // Extraction state
  const [fetchingUrl, setFetchingUrl] = useState(false);
  const [uploadingPdf, setUploadingPdf] = useState(false);
  const [analyzingJd, setAnalyzingJd] = useState(false);
  const [jdFields, setJdFields] = useState<JdExtractedFields | null>(null);

  // Refs for debounce and user-edit tracking
  const analyzeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastAnalyzedRef = useRef("");
  const userEditedRef = useRef<Set<string>>(new Set());

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setJd(initialValues.job_description || "");
      setJobUrl(initialValues.job_url || "");
      setResumeId(initialValues.resume_id);
      setMessageType(initialValues.message_type || "email_detailed");
      setPositionTitle(initialValues.position_title || "");
      setRecruiterName(initialValues.recruiter_name || "");
      setRecipientEmail(initialValues.recipient_email || "");
      userEditedRef.current.clear();
      setJdFields(null);
      lastAnalyzedRef.current = "";
    }
  }, [open, initialValues]);

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
    } catch {
      // silent
    } finally {
      setAnalyzingJd(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    if (analyzeTimerRef.current) clearTimeout(analyzeTimerRef.current);
    if (jd.trim().length >= 100) {
      analyzeTimerRef.current = setTimeout(() => analyzeJd(jd), 1200);
    }
    return () => {
      if (analyzeTimerRef.current) clearTimeout(analyzeTimerRef.current);
    };
  }, [jd, analyzeJd, open]);

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
    if (
      val.match(/^https?:\/\/\S+$/) &&
      val.trim() === val &&
      !jd
    ) {
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

  // ── Save ──

  function handleSave() {
    onSave({
      job_description: jd || undefined,
      job_url: jobUrl || undefined,
      resume_id: resumeId,
      message_type: messageType,
      position_title: positionTitle || undefined,
      recruiter_name: recruiterName || undefined,
      recipient_email: recipientEmail || undefined,
    });
    onClose();
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg bg-[#0a0a0a] border border-[#222] rounded-xl p-6 mx-4 max-h-[90vh] overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-[15px] font-semibold text-[#ededed]">
            Application Context
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-[#666] hover:text-[#ededed] hover:bg-[#111] transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4">
          {/* Job Description */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-[12px] font-medium text-[#888]">
                Job Description
              </label>
              <div className="flex items-center gap-3">
                {analyzingJd && (
                  <span className="flex items-center gap-1 text-[10px] text-[#888]">
                    <Loader2 size={10} className="animate-spin" />
                    Analyzing...
                  </span>
                )}
                <label
                  className={`flex items-center gap-1 text-[11px] cursor-pointer transition-colors ${
                    uploadingPdf
                      ? "text-[#555]"
                      : "text-[#888] hover:text-[#ededed]"
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
              placeholder="Paste a job URL or the full job description here..."
              rows={6}
              className="w-full px-3 py-2.5 rounded-lg bg-[#111] border border-[#222] text-[13px] text-[#ededed] placeholder:text-[#444] focus:outline-none focus:border-[#444] resize-none transition-colors"
            />
          </div>

          {/* Job URL + Resume (side by side) */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[12px] font-medium text-[#888] mb-1.5 flex items-center gap-1.5">
                <LinkIcon size={11} />
                Job URL
                {fetchingUrl && (
                  <span className="text-[10px] text-[#888] font-normal flex items-center gap-1">
                    <Loader2 size={9} className="animate-spin" />
                    extracting...
                  </span>
                )}
              </label>
              <input
                type="text"
                value={jobUrl}
                onChange={(e) => handleJobUrlChange(e.target.value)}
                placeholder="Paste URL to auto-fill"
                className={`w-full px-3 py-2.5 rounded-lg bg-[#111] border text-[13px] text-[#ededed] placeholder:text-[#444] focus:outline-none transition-colors ${
                  fetchingUrl
                    ? "border-[#444]"
                    : "border-[#222] focus:border-[#444]"
                }`}
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[#888] mb-1.5">
                Resume
              </label>
              <select
                value={resumeId ?? ""}
                onChange={(e) =>
                  setResumeId(
                    e.target.value ? Number(e.target.value) : undefined
                  )
                }
                className="w-full px-3 py-2.5 rounded-lg bg-[#111] border border-[#222] text-[13px] text-[#ededed] focus:outline-none focus:border-[#444] transition-colors appearance-none"
              >
                <option value="">Select a resume...</option>
                {resumes.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.title}
                    {r.is_active ? " (Active)" : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Message Type */}
          <div>
            <label className="block text-[12px] font-medium text-[#888] mb-1.5">
              Message Type
            </label>
            <div className="flex flex-wrap gap-1.5">
              {MESSAGE_TYPES.map((mt) => (
                <button
                  key={mt.value}
                  onClick={() => setMessageType(mt.value)}
                  className={`px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors ${
                    messageType === mt.value
                      ? "bg-[#ededed] text-black"
                      : "bg-[#111] text-[#888] border border-[#222] hover:border-[#444] hover:text-[#ededed]"
                  }`}
                >
                  {mt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Position, Recruiter, Email (3 columns) */}
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-[12px] font-medium text-[#888] mb-1.5">
                Position Title
                {isAutoFilled("positionTitle", positionTitle) && (
                  <span className="ml-1 text-[10px] text-[#555] font-normal">
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
                placeholder="e.g. Senior Engineer"
                className="w-full px-3 py-2.5 rounded-lg bg-[#111] border border-[#222] text-[13px] text-[#ededed] placeholder:text-[#444] focus:outline-none focus:border-[#444] transition-colors"
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[#888] mb-1.5">
                Recruiter Name
                {isAutoFilled("recruiterName", recruiterName) && (
                  <span className="ml-1 text-[10px] text-[#555] font-normal">
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
                className="w-full px-3 py-2.5 rounded-lg bg-[#111] border border-[#222] text-[13px] text-[#ededed] placeholder:text-[#444] focus:outline-none focus:border-[#444] transition-colors"
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[#888] mb-1.5">
                Recipient Email
                {isAutoFilled("recipientEmail", recipientEmail) && (
                  <span className="ml-1 text-[10px] text-[#555] font-normal">
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
                placeholder="recruiter@company.com"
                className="w-full px-3 py-2.5 rounded-lg bg-[#111] border border-[#222] text-[13px] text-[#ededed] placeholder:text-[#444] focus:outline-none focus:border-[#444] transition-colors"
              />
            </div>
          </div>
        </div>

        {/* Save */}
        <div className="mt-6 flex justify-end">
          <button
            onClick={handleSave}
            className="px-5 py-2 text-[13px] font-medium bg-[#ededed] text-black rounded-lg hover:bg-white transition-colors"
          >
            Save Context
          </button>
        </div>
      </div>
    </div>
  );
}
