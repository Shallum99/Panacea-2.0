"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { getResumes, type Resume } from "@/lib/api/resumes";
import {
  getSectionMap,
  optimizePDF,
  getDownloadUrl,
  type SectionMapResponse,
  type PDFOptimizeResponse,
} from "@/lib/api/resumeTailor";
import { createClient } from "@/lib/supabase/client";

type Step = "input" | "preview" | "optimizing" | "done";

export default function TailorPage() {
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [loadingResumes, setLoadingResumes] = useState(true);
  const [selectedResumeId, setSelectedResumeId] = useState<number | undefined>();
  const [jobDescription, setJobDescription] = useState("");

  const [step, setStep] = useState<Step>("input");
  const [sectionMap, setSectionMap] = useState<SectionMapResponse | null>(null);
  const [result, setResult] = useState<PDFOptimizeResponse | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

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

  async function handlePreview() {
    if (!jobDescription.trim()) {
      toast.error("Paste a job description first");
      return;
    }
    setLoadingPreview(true);
    try {
      const map = await getSectionMap(jobDescription, selectedResumeId);
      setSectionMap(map);
      setStep("preview");
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response
              ?.data?.detail
          : undefined;
      toast.error(msg || "Failed to analyze PDF sections");
    } finally {
      setLoadingPreview(false);
    }
  }

  async function handleOptimize() {
    setStep("optimizing");
    try {
      const res = await optimizePDF(jobDescription, selectedResumeId);
      setResult(res);
      setStep("done");
      toast.success("Resume optimized — format preserved");
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response
              ?.data?.detail
          : undefined;
      toast.error(msg || "Optimization failed");
      setStep("preview");
    }
  }

  async function handleDownload() {
    if (!result) return;
    // Get token for authenticated download
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();

    const url = getDownloadUrl(result.download_id);
    try {
      const response = await fetch(url, {
        headers: {
          Authorization: `Bearer ${session?.access_token || ""}`,
        },
      });
      if (!response.ok) throw new Error("Download failed");
      const blob = await response.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `tailored_resume_${result.download_id.slice(0, 8)}.pdf`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch {
      toast.error("Download failed");
    }
  }

  function handleReset() {
    setStep("input");
    setSectionMap(null);
    setResult(null);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Tailor Resume</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Optimize your resume PDF while preserving exact formatting
        </p>
      </div>

      {/* Step: Input */}
      {step === "input" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="space-y-4">
            {/* Resume selector */}
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                Resume PDF
              </label>
              {loadingResumes ? (
                <div className="h-9 bg-muted rounded-md animate-pulse" />
              ) : resumes.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  No resumes uploaded.{" "}
                  <a
                    href="/resumes/upload"
                    className="text-accent hover:underline"
                  >
                    Upload one
                  </a>
                </p>
              ) : (
                <select
                  value={selectedResumeId ?? ""}
                  onChange={(e) =>
                    setSelectedResumeId(Number(e.target.value))
                  }
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

            {/* Job description */}
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                Job Description
              </label>
              <textarea
                value={jobDescription}
                onChange={(e) => setJobDescription(e.target.value)}
                rows={16}
                placeholder="Paste the full job description here..."
                className="w-full px-3 py-2 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted-foreground/50 resize-y"
              />
            </div>

            <button
              onClick={handlePreview}
              disabled={loadingPreview || !jobDescription.trim()}
              className="w-full h-10 bg-accent text-accent-foreground text-sm font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {loadingPreview ? "Analyzing PDF..." : "Analyze Sections"}
            </button>
          </div>

          {/* Explainer */}
          <div className="border border-dashed border-border rounded-lg p-8 flex items-center justify-center">
            <div className="text-center space-y-3">
              <p className="text-sm font-medium">How it works</p>
              <div className="text-xs text-muted-foreground space-y-2 text-left max-w-xs">
                <p>1. Paste a job description</p>
                <p>2. We analyze your PDF to detect sections and formatting</p>
                <p>
                  3. AI optimizes content for ATS keywords while preserving{" "}
                  <span className="text-foreground font-medium">
                    exact fonts, layout, and spacing
                  </span>
                </p>
                <p>4. Download the optimized PDF — visually identical</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Step: Preview sections */}
      {step === "preview" && sectionMap && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">
                PDF Analysis: {sectionMap.sections.length} sections detected
              </p>
              <p className="text-xs text-muted-foreground">
                {sectionMap.total_spans} text spans across{" "}
                {sectionMap.total_lines} lines
              </p>
            </div>
            <button
              onClick={handleReset}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Start Over
            </button>
          </div>

          <div className="space-y-2">
            {sectionMap.sections.map((section, i) => (
              <div
                key={i}
                className="border border-border rounded-lg p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium">{section.name}</p>
                  <span className="text-[10px] text-muted-foreground">
                    {section.num_content_lines} lines &middot;{" "}
                    {section.char_count} chars
                  </span>
                </div>
                <p className="text-xs text-muted-foreground line-clamp-3 font-mono">
                  {section.content_text || (
                    <span className="italic">Section header only</span>
                  )}
                </p>
              </div>
            ))}
          </div>

          <button
            onClick={handleOptimize}
            className="w-full h-10 bg-accent text-accent-foreground text-sm font-medium rounded-lg hover:opacity-90 transition-opacity"
          >
            Optimize PDF — Preserve Format
          </button>
        </div>
      )}

      {/* Step: Optimizing */}
      {step === "optimizing" && (
        <div className="border border-border rounded-lg p-12 text-center space-y-4">
          <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto" />
          <div>
            <p className="text-sm font-medium">Optimizing your resume...</p>
            <p className="text-xs text-muted-foreground mt-1">
              Rewriting content while preserving exact formatting. This may take
              30-60 seconds.
            </p>
          </div>
        </div>
      )}

      {/* Step: Done */}
      {step === "done" && result && (
        <div className="space-y-6">
          {/* Score comparison */}
          <div className="grid grid-cols-2 gap-4">
            <div className="border border-border rounded-lg p-6 text-center">
              <p className="text-3xl font-bold">
                {Math.round(result.original_ats_score)}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Original ATS Score
              </p>
            </div>
            <div className="border border-accent/30 bg-accent/5 rounded-lg p-6 text-center">
              <p className="text-3xl font-bold text-accent">
                {Math.round(result.optimized_ats_score)}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Optimized ATS Score
              </p>
              {result.optimized_ats_score > result.original_ats_score && (
                <p className="text-[10px] text-accent mt-0.5">
                  +
                  {Math.round(
                    result.optimized_ats_score - result.original_ats_score
                  )}{" "}
                  points
                </p>
              )}
            </div>
          </div>

          {/* Sections optimized */}
          <div className="border border-border rounded-lg p-4">
            <p className="text-xs font-medium text-muted-foreground mb-2">
              Sections Optimized
            </p>
            <div className="flex flex-wrap gap-1.5">
              {result.sections_found.map((name) => {
                const wasOptimized = result.sections_optimized.includes(name);
                return (
                  <span
                    key={name}
                    className={`text-[10px] px-2 py-0.5 rounded ${
                      wasOptimized
                        ? "bg-accent/10 text-accent"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {name}
                    {wasOptimized ? " (optimized)" : " (unchanged)"}
                  </span>
                );
              })}
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleDownload}
              className="px-6 py-2.5 bg-accent text-accent-foreground text-sm font-medium rounded-lg hover:opacity-90 transition-opacity"
            >
              Download Optimized PDF
            </button>
            <button
              onClick={handleReset}
              className="px-4 py-2.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Optimize Another
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
