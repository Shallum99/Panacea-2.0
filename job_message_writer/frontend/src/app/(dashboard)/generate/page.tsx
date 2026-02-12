"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { toast } from "sonner";
import { createClient } from "@/lib/supabase/client";
import { getResumes, getResumePdfUrl, type Resume } from "@/lib/api/resumes";
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

  const [selectedResumeId, setSelectedResumeId] = useState<number | undefined>();
  const [jobDescription, setJobDescription] = useState("");
  const [messageType, setMessageType] = useState("email_detailed");
  const [recruiterName, setRecruiterName] = useState("");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [positionTitle, setPositionTitle] = useState("");
  const [jobUrl, setJobUrl] = useState("");

  const [analyzingJd, setAnalyzingJd] = useState(false);
  const [jdFields, setJdFields] = useState<JdExtractedFields | null>(null);
  const [uploadingPdf, setUploadingPdf] = useState(false);
  const analyzeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastAnalyzedRef = useRef("");
  const userEditedRef = useRef<Set<string>>(new Set());

  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<Application | null>(null);
  const [streamedText, setStreamedText] = useState("");
  const [editedMessage, setEditedMessage] = useState("");
  const [editedSubject, setEditedSubject] = useState("");
  const [editedRecipient, setEditedRecipient] = useState("");
  const [sending, setSending] = useState(false);

  const [tailoring, setTailoring] = useState(false);
  const [tailorResult, setTailorResult] = useState<PDFOptimizeResponse | null>(null);
  const [attachTailored, setAttachTailored] = useState(false);

  const [activeTab, setActiveTab] = useState<"message" | "resume">("message");
  const [pdfView, setPdfView] = useState<"tailored" | "original" | "diff">("tailored");
  const [originalPdfBlobUrl, setOriginalPdfBlobUrl] = useState<string | null>(null);
  const [tailoredPdfBlobUrl, setTailoredPdfBlobUrl] = useState<string | null>(null);
  const [diffPdfBlobUrl, setDiffPdfBlobUrl] = useState<string | null>(null);
  const [loadingPdf, setLoadingPdf] = useState(false);

  useEffect(() => { loadResumes(); }, []);

  useEffect(() => {
    return () => {
      if (originalPdfBlobUrl) URL.revokeObjectURL(originalPdfBlobUrl);
      if (tailoredPdfBlobUrl) URL.revokeObjectURL(tailoredPdfBlobUrl);
      if (diffPdfBlobUrl) URL.revokeObjectURL(diffPdfBlobUrl);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadResumes() {
    try {
      const data = await getResumes();
      setResumes(data);
      const active = data.find((r) => r.is_active);
      if (active) setSelectedResumeId(active.id);
      else if (data.length > 0) setSelectedResumeId(data[0].id);
    } catch { toast.error("Failed to load resumes"); }
    finally { setLoadingResumes(false); }
  }

  const analyzeJd = useCallback(async (text: string) => {
    if (text.trim().length < 100 || text === lastAnalyzedRef.current) return;
    lastAnalyzedRef.current = text;
    setAnalyzingJd(true);
    try {
      const fields = await extractJdFields(text);
      setJdFields(fields);
      if (fields.position_title && !userEditedRef.current.has("positionTitle")) setPositionTitle(fields.position_title);
      if (fields.recruiter_name && !userEditedRef.current.has("recruiterName")) setRecruiterName(fields.recruiter_name);
      if (fields.recipient_email && !userEditedRef.current.has("recipientEmail")) setRecipientEmail(fields.recipient_email);
    } catch {} finally { setAnalyzingJd(false); }
  }, []);

  useEffect(() => {
    if (analyzeTimerRef.current) clearTimeout(analyzeTimerRef.current);
    if (jobDescription.trim().length >= 100) {
      analyzeTimerRef.current = setTimeout(() => analyzeJd(jobDescription), 1200);
    }
    return () => { if (analyzeTimerRef.current) clearTimeout(analyzeTimerRef.current); };
  }, [jobDescription, analyzeJd]);

  async function handleJdPdfUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingPdf(true);
    try { const { text } = await uploadJdPdf(file); setJobDescription(text); toast.success("JD extracted from PDF"); }
    catch { toast.error("Failed to extract text from PDF"); }
    finally { setUploadingPdf(false); e.target.value = ""; }
  }

  async function fetchPdfBlob(url: string): Promise<string> {
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    const res = await fetch(url, { headers: { Authorization: `Bearer ${session?.access_token || ""}` } });
    if (!res.ok) throw new Error("Failed to fetch PDF");
    return URL.createObjectURL(await res.blob());
  }

  function revokeAllBlobs() {
    if (originalPdfBlobUrl) { URL.revokeObjectURL(originalPdfBlobUrl); setOriginalPdfBlobUrl(null); }
    if (tailoredPdfBlobUrl) { URL.revokeObjectURL(tailoredPdfBlobUrl); setTailoredPdfBlobUrl(null); }
    if (diffPdfBlobUrl) { URL.revokeObjectURL(diffPdfBlobUrl); setDiffPdfBlobUrl(null); }
  }

  // ── Handlers ──

  async function handleGenerate() {
    if (!jobDescription.trim()) { toast.error("Paste a job description first"); return; }
    setGenerating(true); setResult(null); setStreamedText(""); setEditedMessage(""); setEditedSubject(""); setActiveTab("message");
    try {
      await streamApplication(
        {
          job_description: jobDescription, message_type: messageType, resume_id: selectedResumeId,
          recruiter_name: recruiterName || undefined, recipient_email: recipientEmail || undefined,
          position_title: positionTitle || undefined, job_url: jobUrl || undefined,
        },
        (text) => setStreamedText((prev) => prev + text),
        (app) => {
          setResult(app);
          setEditedMessage(app.final_message || app.generated_message || "");
          setEditedSubject(app.subject || "");
          setEditedRecipient(app.recipient_email || recipientEmail || "");
          setGenerating(false); toast.success("Message generated");
        },
        (error) => { toast.error(error || "Failed to generate"); setGenerating(false); },
        async () => { const sb = createClient(); const { data: { session } } = await sb.auth.getSession(); return session?.access_token || null; },
      );
    } catch (err: unknown) { toast.error(err instanceof Error ? err.message : "Failed to generate"); setGenerating(false); }
  }

  async function handleTailor() {
    if (!jobDescription.trim()) { toast.error("Paste a job description first"); return; }
    setTailoring(true); setActiveTab("resume");
    try {
      const res = await optimizePDF(jobDescription, selectedResumeId);
      setTailorResult(res); setAttachTailored(true); setPdfView("tailored");
      // Fetch tailored PDF blob
      try {
        const blobUrl = await fetchPdfBlob(getDownloadUrl(res.download_id));
        if (tailoredPdfBlobUrl) URL.revokeObjectURL(tailoredPdfBlobUrl);
        setTailoredPdfBlobUrl(blobUrl);
      } catch {}
      // Fetch diff PDF blob
      if (res.diff_download_id) {
        try {
          const blobUrl = await fetchPdfBlob(getDownloadUrl(res.diff_download_id));
          if (diffPdfBlobUrl) URL.revokeObjectURL(diffPdfBlobUrl);
          setDiffPdfBlobUrl(blobUrl);
        } catch {}
      }
      toast.success("Resume optimized");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      const message = typeof detail === "object" && detail !== null ? (detail as { message?: string }).message : detail || "Failed to optimize resume";
      toast.error(String(message));
    } finally { setTailoring(false); }
  }

  async function handleDownloadTailored() {
    if (!tailorResult) return;
    try {
      const blobUrl = await fetchPdfBlob(getDownloadUrl(tailorResult.download_id));
      const a = document.createElement("a");
      a.href = blobUrl; a.download = `tailored_resume_${tailorResult.download_id.slice(0, 8)}.pdf`; a.click();
      URL.revokeObjectURL(blobUrl);
    } catch { toast.error("Download failed"); }
  }

  async function handleViewOriginalPdf() {
    setPdfView("original");
    if (originalPdfBlobUrl || !selectedResumeId) return;
    setLoadingPdf(true);
    try { setOriginalPdfBlobUrl(await fetchPdfBlob(getResumePdfUrl(selectedResumeId))); }
    catch { toast.error("Failed to load original PDF"); }
    finally { setLoadingPdf(false); }
  }

  async function handleSend() {
    if (!result || !editedRecipient.trim()) { toast.error("Enter a recipient email"); return; }
    setSending(true);
    try {
      await updateApplication(result.id, { edited_message: editedMessage, subject: editedSubject, recipient_email: editedRecipient });
      setResult(await sendApplication(result.id, attachTailored && tailorResult ? tailorResult.download_id : undefined));
      toast.success("Email sent!");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Failed to send email");
    } finally { setSending(false); }
  }

  function handleReset() {
    setResult(null); setStreamedText(""); setEditedMessage(""); setEditedSubject(""); setEditedRecipient("");
    setTailorResult(null); setAttachTailored(false); setActiveTab("message"); setPdfView("tailored");
    revokeAllBlobs();
  }

  const isAutoFilled = (field: string, value: string) => {
    if (!jdFields || userEditedRef.current.has(field) || !value) return false;
    const key = field === "positionTitle" ? "position_title" : field === "recruiterName" ? "recruiter_name" : "recipient_email";
    return jdFields[key as keyof JdExtractedFields] === value;
  };

  const isSent = result?.status === "sent";
  const hasRightContent = generating || result || tailoring || tailorResult;

  // ── Render ──

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-0" style={{ height: "calc(100vh - 4rem)" }}>

      {/* ═══ LEFT — Inputs ═══ */}
      <div className="xl:overflow-y-auto xl:pr-6 xl:border-r xl:border-border space-y-4 py-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Generate & Tailor</h1>
          <p className="text-sm text-muted-foreground mt-1">Create a message, optimize your resume, or both</p>
        </div>

        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1.5">Resume</label>
          {loadingResumes ? <div className="h-9 bg-muted rounded-md animate-pulse" /> : resumes.length === 0 ? (
            <p className="text-xs text-muted-foreground">No resumes. <a href="/resumes/upload" className="text-accent hover:underline">Upload one</a></p>
          ) : (
            <select value={selectedResumeId ?? ""} onChange={(e) => setSelectedResumeId(Number(e.target.value))}
              className="w-full h-9 px-3 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent">
              {resumes.map((r) => <option key={r.id} value={r.id}>{r.title}{r.is_active ? " (Active)" : ""}</option>)}
            </select>
          )}
        </div>

        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1.5">Message Type</label>
          <div className="flex flex-wrap gap-1.5">
            {MESSAGE_TYPES.map((t) => (
              <button key={t.value} onClick={() => setMessageType(t.value)}
                className={`px-3 py-1.5 text-xs rounded-md border transition-colors ${messageType === t.value ? "border-accent bg-accent/10 text-accent" : "border-border text-muted-foreground hover:text-foreground hover:border-muted-foreground"}`}>
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">
              Position Title {isAutoFilled("positionTitle", positionTitle) && <span className="text-[10px] text-accent ml-1 font-normal">auto-detected</span>}
            </label>
            <input value={positionTitle} onChange={(e) => { userEditedRef.current.add("positionTitle"); setPositionTitle(e.target.value); }}
              placeholder="e.g. Senior Engineer" className="w-full h-9 px-3 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted-foreground/50" />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">
              Recruiter Name {isAutoFilled("recruiterName", recruiterName) && <span className="text-[10px] text-accent ml-1 font-normal">auto-detected</span>}
            </label>
            <input value={recruiterName} onChange={(e) => { userEditedRef.current.add("recruiterName"); setRecruiterName(e.target.value); }}
              placeholder="Optional" className="w-full h-9 px-3 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted-foreground/50" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">
              Recipient Email {isAutoFilled("recipientEmail", recipientEmail) && <span className="text-[10px] text-accent ml-1 font-normal">auto-detected</span>}
            </label>
            <input type="email" value={recipientEmail} onChange={(e) => { userEditedRef.current.add("recipientEmail"); setRecipientEmail(e.target.value); }}
              placeholder="recruiter@company.com" className="w-full h-9 px-3 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted-foreground/50" />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">Job URL</label>
            <input value={jobUrl} onChange={(e) => setJobUrl(e.target.value)} placeholder="https://..."
              className="w-full h-9 px-3 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted-foreground/50" />
          </div>
        </div>

        <div className="flex-1 flex flex-col">
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs font-medium text-muted-foreground">Job Description</label>
            <div className="flex items-center gap-3">
              {analyzingJd && <span className="text-[10px] text-accent animate-pulse">Analyzing JD...</span>}
              <label className={`text-xs cursor-pointer transition-colors ${uploadingPdf ? "text-muted-foreground" : "text-accent hover:text-accent/80"}`}>
                {uploadingPdf ? "Extracting..." : "Upload PDF"}
                <input type="file" accept=".pdf" className="hidden" onChange={handleJdPdfUpload} disabled={uploadingPdf} />
              </label>
            </div>
          </div>
          <textarea value={jobDescription} onChange={(e) => setJobDescription(e.target.value)}
            placeholder="Paste the full job description here or upload a PDF..."
            className="w-full flex-1 min-h-[180px] px-3 py-2 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted-foreground/50 resize-y" />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <button onClick={handleGenerate} disabled={generating || !jobDescription.trim()}
            className="h-10 bg-accent text-accent-foreground text-sm font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed">
            {generating ? "Generating..." : "Generate Message"}
          </button>
          <button onClick={handleTailor} disabled={tailoring || !jobDescription.trim()}
            className="h-10 border border-accent text-accent text-sm font-medium rounded-lg hover:bg-accent/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
            {tailoring ? "Optimizing..." : "Tailor Resume"}
          </button>
        </div>
      </div>

      {/* ═══ RIGHT — Viewer (starts at very top) ═══ */}
      <div className="xl:pl-6 flex flex-col min-h-0 py-4">

        {/* Tab bar + compact ATS score (always at top) */}
        <div className="shrink-0">
          {hasRightContent ? (
            <div className="flex items-center justify-between border-b border-border">
              <div className="flex">
                <button onClick={() => setActiveTab("message")}
                  className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${activeTab === "message" ? "border-accent text-accent" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
                  Message
                  {result && <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent">{isSent ? "sent" : "ready"}</span>}
                </button>
                <button onClick={() => setActiveTab("resume")}
                  className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${activeTab === "resume" ? "border-accent text-accent" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
                  Resume
                  {tailorResult && <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-green-500/10 text-green-500">+{Math.round(tailorResult.optimized_ats_score - tailorResult.original_ats_score)} ATS</span>}
                  {tailoring && <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent animate-pulse">optimizing</span>}
                </button>
              </div>
              {/* Compact ATS score in tab bar */}
              {activeTab === "resume" && tailorResult && (
                <div className="flex items-center gap-3 pr-1 text-xs">
                  <span className="text-muted-foreground">ATS</span>
                  <span className="font-mono font-bold">{Math.round(tailorResult.original_ats_score)}</span>
                  <svg className="w-3.5 h-3.5 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>
                  <span className="font-mono font-bold text-accent">{Math.round(tailorResult.optimized_ats_score)}</span>
                  <span className="text-green-500 font-medium">(+{Math.round(tailorResult.optimized_ats_score - tailorResult.original_ats_score)})</span>
                </div>
              )}
            </div>
          ) : (
            <div className="border-b border-border py-2.5 px-1">
              <p className="text-sm text-muted-foreground">Preview</p>
            </div>
          )}
        </div>

        {/* Resume sub-nav: Tailored / Original / Diff */}
        {activeTab === "resume" && tailorResult && (
          <div className="shrink-0 px-1 py-2 border-b border-border flex items-center gap-1">
            {(["tailored", "original", "diff"] as const).map((view) => (
              <button key={view} onClick={() => view === "original" ? handleViewOriginalPdf() : setPdfView(view)}
                className={`px-3 py-1 text-xs rounded-md transition-colors ${pdfView === view ? "bg-accent/10 text-accent font-medium" : "text-muted-foreground hover:text-foreground"}`}>
                {view === "tailored" ? "Tailored PDF" : view === "original" ? "Original PDF" : `Diff (${tailorResult.changes.length})`}
              </button>
            ))}
          </div>
        )}

        {/* Content — fills all remaining height */}
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">

          {/* ── MESSAGE TAB ── */}
          {activeTab === "message" && (
            <div className="flex-1 min-h-0 flex flex-col">
              {generating ? (
                streamedText ? (
                  <div className="flex-1 flex flex-col border border-accent/30 rounded-lg overflow-hidden mt-2">
                    <div className="px-4 py-3 border-b border-border flex items-center gap-2 shrink-0">
                      <div className="h-2 w-2 bg-accent rounded-full animate-pulse" />
                      <p className="text-sm font-medium text-muted-foreground">Generating...</p>
                    </div>
                    <div className="px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap flex-1 overflow-y-auto">
                      {streamedText}
                      <span className="inline-block w-2 h-4 bg-accent/70 animate-pulse ml-0.5 align-text-bottom" />
                    </div>
                  </div>
                ) : (
                  <div className="border border-border rounded-lg p-6 space-y-3 animate-pulse mt-2">
                    <div className="h-4 bg-muted rounded w-1/3" />
                    <div className="h-3 bg-muted rounded w-full" />
                    <div className="h-3 bg-muted rounded w-5/6" />
                    <div className="h-3 bg-muted rounded w-4/6" />
                    <div className="h-3 bg-muted rounded w-full" />
                    <div className="h-3 bg-muted rounded w-3/4" />
                  </div>
                )
              ) : result ? (
                <div className="flex-1 flex flex-col border border-border rounded-lg overflow-hidden mt-2 min-h-0">
                  <div className="px-4 py-3 border-b border-border flex items-center justify-between shrink-0">
                    <div>
                      <p className="text-sm font-medium">{result.company_name || "Application"}</p>
                      <p className="text-xs text-muted-foreground">{result.position_title || result.message_type}</p>
                    </div>
                    <span className={`text-[10px] font-medium px-2 py-0.5 rounded ${isSent ? "bg-green-500/10 text-green-500" : "bg-accent/10 text-accent"}`}>
                      {isSent ? "sent" : result.status.replace("_", " ")}
                    </span>
                  </div>
                  <div className="px-4 py-2 border-b border-border shrink-0">
                    <label className="text-[10px] text-muted-foreground uppercase tracking-wider">Subject</label>
                    <input value={editedSubject} onChange={(e) => setEditedSubject(e.target.value)} disabled={isSent}
                      className="w-full text-sm bg-transparent border-none focus:outline-none mt-0.5 disabled:opacity-60" placeholder="Email subject line..." />
                  </div>
                  <div className="px-4 py-2 border-b border-border shrink-0">
                    <label className="text-[10px] text-muted-foreground uppercase tracking-wider">To</label>
                    <input type="email" value={editedRecipient} onChange={(e) => setEditedRecipient(e.target.value)} disabled={isSent}
                      className="w-full text-sm bg-transparent border-none focus:outline-none mt-0.5 disabled:opacity-60" placeholder="recruiter@company.com" />
                  </div>
                  <textarea value={editedMessage} onChange={(e) => setEditedMessage(e.target.value)} disabled={isSent}
                    className="w-full flex-1 min-h-0 px-4 py-3 text-sm bg-background border-none focus:outline-none resize-none leading-relaxed disabled:opacity-60" />
                  {tailorResult && !isSent && (
                    <div className="px-4 py-2 border-t border-border shrink-0">
                      <label className="flex items-center gap-2 text-sm cursor-pointer">
                        <input type="checkbox" checked={attachTailored} onChange={(e) => setAttachTailored(e.target.checked)} className="rounded border-border" />
                        <span className="text-muted-foreground">Attach tailored resume <span className="text-[10px] text-green-500 ml-1">(ATS {Math.round(tailorResult.optimized_ats_score)})</span></span>
                      </label>
                    </div>
                  )}
                  <div className="px-4 py-3 border-t border-border flex items-center gap-2 shrink-0">
                    {isSent ? (
                      <div className="flex items-center gap-2 text-sm text-green-500">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                        Email sent {result.resume_id && <span className="text-xs text-muted-foreground ml-1">with resume attached</span>}
                      </div>
                    ) : (
                      <button onClick={handleSend} disabled={sending || !editedRecipient.trim()}
                        className="px-4 py-2 text-sm font-medium bg-accent text-accent-foreground rounded-md hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed">
                        {sending ? "Sending..." : "Send Email"}
                      </button>
                    )}
                    <button onClick={handleReset} className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
                      {isSent ? "New Message" : "Discard"}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex-1 border border-dashed border-border rounded-lg flex items-center justify-center mt-2">
                  <p className="text-sm text-muted-foreground text-center">
                    Paste a job description and click Generate<br />
                    <span className="text-xs opacity-60">The AI will craft a personalized message using your resume</span>
                  </p>
                </div>
              )}
            </div>
          )}

          {/* ── RESUME TAB ── */}
          {activeTab === "resume" && (
            <div className="flex-1 min-h-0 flex flex-col">
              {tailoring ? (
                <div className="flex-1 border border-border rounded-lg flex items-center justify-center mt-2">
                  <div className="text-center space-y-4">
                    <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto" />
                    <p className="text-sm font-medium">Optimizing your resume...</p>
                    <p className="text-xs text-muted-foreground">Preserving exact formatting. 30-60 seconds.</p>
                  </div>
                </div>
              ) : tailorResult ? (
                <div className="flex-1 flex flex-col min-h-0">
                  {/* PDF viewer — fills all space */}
                  <div className="flex-1 min-h-0 relative mt-2 rounded-lg overflow-hidden border border-border">
                    {pdfView === "tailored" && (
                      tailoredPdfBlobUrl ? (
                        <iframe src={tailoredPdfBlobUrl} className="absolute inset-0 w-full h-full border-0" title="Tailored Resume PDF" />
                      ) : (
                        <div className="absolute inset-0 flex items-center justify-center">
                          <div className="text-center space-y-2">
                            <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto" />
                            <p className="text-xs text-muted-foreground">Loading PDF...</p>
                          </div>
                        </div>
                      )
                    )}
                    {pdfView === "original" && (
                      loadingPdf ? (
                        <div className="absolute inset-0 flex items-center justify-center">
                          <div className="text-center space-y-2">
                            <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto" />
                            <p className="text-xs text-muted-foreground">Loading original PDF...</p>
                          </div>
                        </div>
                      ) : originalPdfBlobUrl ? (
                        <iframe src={originalPdfBlobUrl} className="absolute inset-0 w-full h-full border-0" title="Original Resume PDF" />
                      ) : (
                        <div className="absolute inset-0 flex items-center justify-center">
                          <p className="text-xs text-muted-foreground">Could not load original PDF</p>
                        </div>
                      )
                    )}
                    {pdfView === "diff" && (
                      diffPdfBlobUrl ? (
                        <iframe src={diffPdfBlobUrl} className="absolute inset-0 w-full h-full border-0" title="Resume Diff — green highlights show changes" />
                      ) : (
                        <div className="absolute inset-0 flex items-center justify-center">
                          <div className="text-center space-y-2">
                            <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto" />
                            <p className="text-xs text-muted-foreground">Loading diff PDF...</p>
                          </div>
                        </div>
                      )
                    )}
                  </div>

                  {/* Actions bar */}
                  <div className="px-1 py-3 flex items-center gap-3 shrink-0">
                    <button onClick={handleDownloadTailored}
                      className="px-4 py-2 text-sm font-medium bg-accent text-accent-foreground rounded-md hover:opacity-90 transition-opacity">
                      Download PDF
                    </button>
                    <button onClick={() => { setTailorResult(null); setAttachTailored(false); revokeAllBlobs(); }}
                      className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
                      Re-tailor
                    </button>
                    {result && (
                      <label className="flex items-center gap-2 text-sm cursor-pointer ml-auto">
                        <input type="checkbox" checked={attachTailored} onChange={(e) => setAttachTailored(e.target.checked)} className="rounded border-border" />
                        <span className="text-muted-foreground">Attach to email</span>
                      </label>
                    )}
                  </div>
                </div>
              ) : (
                <div className="flex-1 border border-dashed border-border rounded-lg flex items-center justify-center mt-2">
                  <p className="text-sm text-muted-foreground text-center">
                    Click &quot;Tailor Resume&quot; to optimize for this JD<br />
                    <span className="text-xs opacity-60">Preserves exact formatting while boosting ATS keyword match</span>
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
