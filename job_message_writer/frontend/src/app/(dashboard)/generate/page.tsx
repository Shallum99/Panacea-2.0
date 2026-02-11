"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { toast } from "sonner";
import { createClient } from "@/lib/supabase/client";
import { getResumes, type Resume } from "@/lib/api/resumes";
import {
  streamApplication,
  extractJdFields,
  uploadJdPdf,
  updateApplication,
  sendApplication,
  type Application,
  type CreateApplicationRequest,
  type JdExtractedFields,
} from "@/lib/api/applications";
import {
  optimizePDF,
  getDownloadUrl,
  type PDFOptimizeResponse,
} from "@/lib/api/resumeTailor";

const MESSAGE_TYPES = [
  { value: "email_detailed", label: "Detailed Email" },
  { value: "email_short", label: "Short Email" },
  { value: "linkedin_message", label: "LinkedIn Message" },
  { value: "linkedin_connection", label: "LinkedIn Connection" },
  { value: "linkedin_inmail", label: "LinkedIn InMail" },
  { value: "ycombinator", label: "Y Combinator" },
];

export default function GeneratePage() {
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

  // JD analysis state
  const [analyzingJd, setAnalyzingJd] = useState(false);
  const [jdFields, setJdFields] = useState<JdExtractedFields | null>(null);
  const [uploadingPdf, setUploadingPdf] = useState(false);
  const analyzeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastAnalyzedRef = useRef("");
  const userEditedRef = useRef<Set<string>>(new Set());

  // Message result state
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<Application | null>(null);
  const [streamedText, setStreamedText] = useState("");
  const [editedMessage, setEditedMessage] = useState("");
  const [editedSubject, setEditedSubject] = useState("");
  const [editedRecipient, setEditedRecipient] = useState("");
  const [sending, setSending] = useState(false);

  // Tailor state
  const [tailoring, setTailoring] = useState(false);
  const [tailorResult, setTailorResult] = useState<PDFOptimizeResponse | null>(null);
  const [attachTailored, setAttachTailored] = useState(false);

  // Tab state for right panel
  const [activeTab, setActiveTab] = useState<"message" | "resume">("message");

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

  // Debounced JD analysis
  const analyzeJd = useCallback(async (text: string) => {
    if (text.trim().length < 100) return;
    if (text === lastAnalyzedRef.current) return;
    lastAnalyzedRef.current = text;

    setAnalyzingJd(true);
    try {
      const fields = await extractJdFields(text);
      setJdFields(fields);
      if (fields.position_title && !userEditedRef.current.has("positionTitle")) {
        setPositionTitle(fields.position_title);
      }
      if (fields.recruiter_name && !userEditedRef.current.has("recruiterName")) {
        setRecruiterName(fields.recruiter_name);
      }
      if (fields.recipient_email && !userEditedRef.current.has("recipientEmail")) {
        setRecipientEmail(fields.recipient_email);
      }
    } catch {
      // Silent fail
    } finally {
      setAnalyzingJd(false);
    }
  }, []);

  useEffect(() => {
    if (analyzeTimerRef.current) clearTimeout(analyzeTimerRef.current);
    if (jobDescription.trim().length >= 100) {
      analyzeTimerRef.current = setTimeout(() => analyzeJd(jobDescription), 1200);
    }
    return () => {
      if (analyzeTimerRef.current) clearTimeout(analyzeTimerRef.current);
    };
  }, [jobDescription, analyzeJd]);

  async function handleJdPdfUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingPdf(true);
    try {
      const { text } = await uploadJdPdf(file);
      setJobDescription(text);
      toast.success("JD extracted from PDF");
    } catch {
      toast.error("Failed to extract text from PDF");
    } finally {
      setUploadingPdf(false);
      e.target.value = "";
    }
  }

  async function handleGenerate() {
    if (!jobDescription.trim()) {
      toast.error("Paste a job description first");
      return;
    }
    setGenerating(true);
    setResult(null);
    setStreamedText("");
    setEditedMessage("");
    setEditedSubject("");
    setActiveTab("message");

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
        (text) => setStreamedText((prev) => prev + text),
        (app) => {
          setResult(app);
          setEditedMessage(app.final_message || app.generated_message || "");
          setEditedSubject(app.subject || "");
          setEditedRecipient(app.recipient_email || recipientEmail || "");
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

  async function handleTailor() {
    if (!jobDescription.trim()) {
      toast.error("Paste a job description first");
      return;
    }
    setTailoring(true);
    setActiveTab("resume");
    try {
      const res = await optimizePDF(jobDescription, selectedResumeId);
      setTailorResult(res);
      setAttachTailored(true);
      toast.success("Resume optimized");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Failed to optimize resume");
    } finally {
      setTailoring(false);
    }
  }

  async function handleDownloadTailored() {
    if (!tailorResult) return;
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    const url = getDownloadUrl(tailorResult.download_id);
    try {
      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${session?.access_token || ""}` },
      });
      if (!response.ok) throw new Error("Download failed");
      const blob = await response.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `tailored_resume_${tailorResult.download_id.slice(0, 8)}.pdf`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch {
      toast.error("Download failed");
    }
  }

  async function handleSend() {
    if (!result) return;
    if (!editedRecipient.trim()) {
      toast.error("Enter a recipient email to send");
      return;
    }
    setSending(true);
    try {
      await updateApplication(result.id, {
        edited_message: editedMessage,
        subject: editedSubject,
        recipient_email: editedRecipient,
      });
      const sent = await sendApplication(
        result.id,
        attachTailored && tailorResult ? tailorResult.download_id : undefined,
      );
      setResult(sent);
      toast.success("Email sent!");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Failed to send email");
    } finally {
      setSending(false);
    }
  }

  function handleNewMessage() {
    setResult(null);
    setStreamedText("");
    setEditedMessage("");
    setEditedSubject("");
    setEditedRecipient("");
    setTailorResult(null);
    setAttachTailored(false);
    setActiveTab("message");
  }

  const isAutoFilled = (field: string, value: string) => {
    if (!jdFields || userEditedRef.current.has(field) || !value) return false;
    const key = field === "positionTitle" ? "position_title"
      : field === "recruiterName" ? "recruiter_name"
      : "recipient_email";
    return jdFields[key as keyof JdExtractedFields] === value;
  };

  const isSent = result?.status === "sent";
  const hasRightContent = generating || result || tailoring || tailorResult;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Generate & Tailor</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Create a message, optimize your resume, or both
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_1fr] gap-8">
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
                {isAutoFilled("positionTitle", positionTitle) && (
                  <span className="text-[10px] text-accent ml-1 font-normal">auto-detected</span>
                )}
              </label>
              <input
                value={positionTitle}
                onChange={(e) => {
                  userEditedRef.current.add("positionTitle");
                  setPositionTitle(e.target.value);
                }}
                placeholder="e.g. Senior Engineer"
                className="w-full h-9 px-3 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted-foreground/50"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                Recruiter Name
                {isAutoFilled("recruiterName", recruiterName) && (
                  <span className="text-[10px] text-accent ml-1 font-normal">auto-detected</span>
                )}
              </label>
              <input
                value={recruiterName}
                onChange={(e) => {
                  userEditedRef.current.add("recruiterName");
                  setRecruiterName(e.target.value);
                }}
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
                {isAutoFilled("recipientEmail", recipientEmail) && (
                  <span className="text-[10px] text-accent ml-1 font-normal">auto-detected</span>
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
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                Job Description
              </label>
              <div className="flex items-center gap-3">
                {analyzingJd && (
                  <span className="text-[10px] text-accent animate-pulse">
                    Analyzing JD...
                  </span>
                )}
                <label className={`text-xs cursor-pointer transition-colors ${
                  uploadingPdf ? "text-muted-foreground" : "text-accent hover:text-accent/80"
                }`}>
                  {uploadingPdf ? "Extracting..." : "Upload PDF"}
                  <input
                    type="file"
                    accept=".pdf"
                    className="hidden"
                    onChange={handleJdPdfUpload}
                    disabled={uploadingPdf}
                  />
                </label>
              </div>
            </div>
            <textarea
              value={jobDescription}
              onChange={(e) => setJobDescription(e.target.value)}
              rows={14}
              placeholder="Paste the full job description here or upload a PDF..."
              className="w-full px-3 py-2 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted-foreground/50 resize-y"
            />
          </div>

          {/* Action buttons */}
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={handleGenerate}
              disabled={generating || !jobDescription.trim()}
              className="h-10 bg-accent text-accent-foreground text-sm font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {generating ? "Generating..." : "Generate Message"}
            </button>
            <button
              onClick={handleTailor}
              disabled={tailoring || !jobDescription.trim()}
              className="h-10 border border-accent text-accent text-sm font-medium rounded-lg hover:bg-accent/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {tailoring ? "Optimizing..." : "Tailor Resume"}
            </button>
          </div>
        </div>

        {/* Right column — tabbed results */}
        <div>
          {/* Tab bar — only show when there's content */}
          {hasRightContent && (
            <div className="flex border-b border-border mb-0">
              <button
                onClick={() => setActiveTab("message")}
                className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === "message"
                    ? "border-accent text-accent"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                Message
                {result && (
                  <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent">
                    {isSent ? "sent" : "ready"}
                  </span>
                )}
              </button>
              <button
                onClick={() => setActiveTab("resume")}
                className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === "resume"
                    ? "border-accent text-accent"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                Resume
                {tailorResult && (
                  <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-green-500/10 text-green-500">
                    +{Math.round(tailorResult.optimized_ats_score - tailorResult.original_ats_score)} ATS
                  </span>
                )}
                {tailoring && (
                  <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent animate-pulse">
                    optimizing
                  </span>
                )}
              </button>
            </div>
          )}

          {/* Message tab */}
          {activeTab === "message" && (
            <>
              {generating ? (
                streamedText ? (
                  <div className="border border-accent/30 rounded-b-lg overflow-hidden">
                    <div className="px-4 py-3 border-b border-border flex items-center gap-2">
                      <div className="h-2 w-2 bg-accent rounded-full animate-pulse" />
                      <p className="text-sm font-medium text-muted-foreground">Generating...</p>
                    </div>
                    <div className="px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap min-h-[300px] max-h-[500px] overflow-y-auto">
                      {streamedText}
                      <span className="inline-block w-2 h-4 bg-accent/70 animate-pulse ml-0.5 align-text-bottom" />
                    </div>
                  </div>
                ) : (
                  <div className="border border-border rounded-b-lg p-6 space-y-3 animate-pulse">
                    <div className="h-4 bg-muted rounded w-1/3" />
                    <div className="h-3 bg-muted rounded w-full" />
                    <div className="h-3 bg-muted rounded w-5/6" />
                    <div className="h-3 bg-muted rounded w-4/6" />
                    <div className="h-3 bg-muted rounded w-full" />
                    <div className="h-3 bg-muted rounded w-3/4" />
                  </div>
                )
              ) : result ? (
                <div className="border border-border rounded-b-lg overflow-hidden">
                  {/* Header */}
                  <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">
                        {result.company_name || "Application"}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {result.position_title || result.message_type}
                      </p>
                    </div>
                    <span className={`text-[10px] font-medium px-2 py-0.5 rounded ${
                      isSent
                        ? "bg-green-500/10 text-green-500"
                        : "bg-accent/10 text-accent"
                    }`}>
                      {isSent ? "sent" : result.status.replace("_", " ")}
                    </span>
                  </div>

                  {/* Subject line */}
                  <div className="px-4 py-2 border-b border-border">
                    <label className="text-[10px] text-muted-foreground uppercase tracking-wider">Subject</label>
                    <input
                      value={editedSubject}
                      onChange={(e) => setEditedSubject(e.target.value)}
                      disabled={isSent}
                      className="w-full text-sm bg-transparent border-none focus:outline-none mt-0.5 disabled:opacity-60"
                      placeholder="Email subject line..."
                    />
                  </div>

                  {/* Recipient */}
                  <div className="px-4 py-2 border-b border-border">
                    <label className="text-[10px] text-muted-foreground uppercase tracking-wider">To</label>
                    <input
                      type="email"
                      value={editedRecipient}
                      onChange={(e) => setEditedRecipient(e.target.value)}
                      disabled={isSent}
                      className="w-full text-sm bg-transparent border-none focus:outline-none mt-0.5 disabled:opacity-60"
                      placeholder="recruiter@company.com"
                    />
                  </div>

                  {/* Message body */}
                  <textarea
                    value={editedMessage}
                    onChange={(e) => setEditedMessage(e.target.value)}
                    disabled={isSent}
                    rows={16}
                    className="w-full px-4 py-3 text-sm bg-background border-none focus:outline-none resize-y leading-relaxed disabled:opacity-60"
                  />

                  {/* Attach tailored resume option */}
                  {tailorResult && !isSent && (
                    <div className="px-4 py-2 border-t border-border">
                      <label className="flex items-center gap-2 text-sm cursor-pointer">
                        <input
                          type="checkbox"
                          checked={attachTailored}
                          onChange={(e) => setAttachTailored(e.target.checked)}
                          className="rounded border-border"
                        />
                        <span className="text-muted-foreground">
                          Attach tailored resume
                          <span className="text-[10px] text-green-500 ml-1">
                            (ATS {Math.round(tailorResult.optimized_ats_score)})
                          </span>
                        </span>
                      </label>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="px-4 py-3 border-t border-border flex items-center gap-2">
                    {isSent ? (
                      <div className="flex items-center gap-2 text-sm text-green-500">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                        Email sent
                        {result.resume_id && (
                          <span className="text-xs text-muted-foreground ml-1">with resume attached</span>
                        )}
                      </div>
                    ) : (
                      <button
                        onClick={handleSend}
                        disabled={sending || !editedRecipient.trim()}
                        className="px-4 py-2 text-sm font-medium bg-accent text-accent-foreground rounded-md hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        {sending ? "Sending..." : "Send Email"}
                      </button>
                    )}
                    <button
                      onClick={handleNewMessage}
                      className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
                    >
                      {isSent ? "New Message" : "Discard"}
                    </button>
                  </div>
                </div>
              ) : (
                <div className={`border border-dashed border-border p-12 flex items-center justify-center h-full ${hasRightContent ? "rounded-b-lg" : "rounded-lg"}`}>
                  <p className="text-sm text-muted-foreground text-center">
                    Paste a job description and click Generate
                    <br />
                    <span className="text-xs opacity-60">
                      The AI will craft a personalized message using your resume
                    </span>
                  </p>
                </div>
              )}
            </>
          )}

          {/* Resume tab */}
          {activeTab === "resume" && (
            <>
              {tailoring ? (
                <div className="border border-border rounded-b-lg p-12 text-center space-y-4">
                  <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto" />
                  <div>
                    <p className="text-sm font-medium">Optimizing your resume...</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Rewriting content while preserving exact formatting. This may take 30-60 seconds.
                    </p>
                  </div>
                </div>
              ) : tailorResult ? (
                <div className="border border-border rounded-b-lg overflow-hidden">
                  {/* ATS Score comparison */}
                  <div className="grid grid-cols-2 border-b border-border">
                    <div className="p-6 text-center border-r border-border">
                      <p className="text-3xl font-bold">{Math.round(tailorResult.original_ats_score)}</p>
                      <p className="text-xs text-muted-foreground mt-1">Original ATS Score</p>
                    </div>
                    <div className="p-6 text-center bg-accent/5">
                      <p className="text-3xl font-bold text-accent">{Math.round(tailorResult.optimized_ats_score)}</p>
                      <p className="text-xs text-muted-foreground mt-1">Optimized ATS Score</p>
                      {tailorResult.optimized_ats_score > tailorResult.original_ats_score && (
                        <p className="text-[10px] text-accent mt-0.5">
                          +{Math.round(tailorResult.optimized_ats_score - tailorResult.original_ats_score)} points
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Sections optimized */}
                  <div className="px-4 py-4 border-b border-border">
                    <p className="text-xs font-medium text-muted-foreground mb-2">Sections</p>
                    <div className="flex flex-wrap gap-1.5">
                      {tailorResult.sections_found.map((name) => {
                        const wasOptimized = tailorResult.sections_optimized.includes(name);
                        return (
                          <span
                            key={name}
                            className={`text-[10px] px-2 py-0.5 rounded ${
                              wasOptimized
                                ? "bg-accent/10 text-accent"
                                : "bg-muted text-muted-foreground"
                            }`}
                          >
                            {name} {wasOptimized ? "(optimized)" : "(unchanged)"}
                          </span>
                        );
                      })}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="px-4 py-3 flex items-center gap-3">
                    <button
                      onClick={handleDownloadTailored}
                      className="px-4 py-2 text-sm font-medium bg-accent text-accent-foreground rounded-md hover:opacity-90 transition-opacity"
                    >
                      Download Tailored PDF
                    </button>
                    <button
                      onClick={() => {
                        setTailorResult(null);
                        setAttachTailored(false);
                      }}
                      className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
                    >
                      Re-tailor
                    </button>
                    {result && (
                      <label className="flex items-center gap-2 text-sm cursor-pointer ml-auto">
                        <input
                          type="checkbox"
                          checked={attachTailored}
                          onChange={(e) => setAttachTailored(e.target.checked)}
                          className="rounded border-border"
                        />
                        <span className="text-muted-foreground">Attach to email</span>
                      </label>
                    )}
                  </div>
                </div>
              ) : (
                <div className="border border-dashed border-border rounded-b-lg p-12 flex items-center justify-center h-full">
                  <p className="text-sm text-muted-foreground text-center">
                    Click &quot;Tailor Resume&quot; to optimize for this JD
                    <br />
                    <span className="text-xs opacity-60">
                      Preserves exact formatting while boosting ATS keyword match
                    </span>
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
