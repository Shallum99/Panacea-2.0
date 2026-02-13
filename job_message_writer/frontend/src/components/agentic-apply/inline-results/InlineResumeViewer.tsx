"use client";

import { useState, useEffect, useRef } from "react";
import { Download, ArrowRight, Loader2 } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

interface TailorData {
  resume_title?: string;
  download_id?: string;
  diff_download_id?: string;
  sections_optimized?: string[];
  changes?: Array<{ section: string; type: string; original: string; optimized: string }>;
  ats_score_before?: number;
  ats_score_after?: number;
}

interface Props {
  data: TailorData;
}

async function fetchPdfBlob(downloadId: string): Promise<string | null> {
  try {
    const baseUrl =
      process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
    let token: string | null = null;
    if (process.env.NEXT_PUBLIC_DEV_MODE !== "true") {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      token = session?.access_token ?? null;
    }
    const res = await fetch(
      `${baseUrl}/resume-tailor/download/${downloadId}`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} }
    );
    if (!res.ok) return null;
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  } catch {
    return null;
  }
}

export default function InlineResumeViewer({ data }: Props) {
  const [pdfView, setPdfView] = useState<"tailored" | "diff">("tailored");
  const [tailoredUrl, setTailoredUrl] = useState<string | null>(null);
  const [diffUrl, setDiffUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const urlsRef = useRef<string[]>([]);

  useEffect(() => {
    if (!data.download_id) return;

    setLoading(true);
    const loads: Promise<void>[] = [];

    loads.push(
      fetchPdfBlob(data.download_id).then((url) => {
        if (url) {
          urlsRef.current.push(url);
          setTailoredUrl(url);
        }
      })
    );

    if (data.diff_download_id) {
      loads.push(
        fetchPdfBlob(data.diff_download_id).then((url) => {
          if (url) {
            urlsRef.current.push(url);
            setDiffUrl(url);
          }
        })
      );
    }

    Promise.all(loads).finally(() => setLoading(false));

    return () => {
      urlsRef.current.forEach((u) => URL.revokeObjectURL(u));
      urlsRef.current = [];
    };
  }, [data.download_id, data.diff_download_id]);

  const scoreDelta =
    data.ats_score_after != null && data.ats_score_before != null
      ? Math.round(data.ats_score_after - data.ats_score_before)
      : null;

  const changeCount = data.changes?.length ?? 0;
  const activeUrl = pdfView === "diff" ? diffUrl : tailoredUrl;

  return (
    <div className="flex flex-col h-full">
      {/* Sub-nav: view toggle + ATS score + download */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#222] shrink-0">
        <div className="flex items-center gap-1">
          {(["tailored", "diff"] as const).map((view) => (
            <button
              key={view}
              onClick={() => setPdfView(view)}
              disabled={view === "diff" && !diffUrl}
              className={`px-2.5 py-1 text-[11px] rounded-md transition-colors ${
                pdfView === view
                  ? "bg-[#1a1a1a] text-[#ededed] font-medium"
                  : "text-[#666] hover:text-[#888]"
              } ${view === "diff" && !diffUrl ? "opacity-40 cursor-not-allowed" : ""}`}
            >
              {view === "tailored"
                ? "Tailored"
                : `Diff${changeCount > 0 ? ` (${changeCount})` : ""}`}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3">
          {/* ATS score */}
          {data.ats_score_before != null && data.ats_score_after != null && (
            <div className="flex items-center gap-2 text-[11px]">
              <span className="text-[#666]">ATS</span>
              <span className="font-mono font-bold text-[#ededed]">
                {Math.round(data.ats_score_before)}
              </span>
              <ArrowRight size={10} className="text-[#555]" />
              <span className="font-mono font-bold text-[#ededed]">
                {Math.round(data.ats_score_after)}
              </span>
              {scoreDelta != null && scoreDelta > 0 && (
                <span className="text-[#50e3c2] font-medium">
                  (+{scoreDelta})
                </span>
              )}
            </div>
          )}

          {/* Download */}
          {tailoredUrl && (
            <a
              href={tailoredUrl}
              download={`tailored-${data.resume_title || "resume"}.pdf`}
              className="flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium rounded-md bg-[#ededed] text-black hover:bg-white transition-colors"
            >
              <Download size={11} />
              Download
            </a>
          )}
        </div>
      </div>

      {/* PDF viewer — fills remaining height */}
      <div className="flex-1 relative min-h-0">
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center space-y-2">
              <Loader2 size={18} className="animate-spin text-[#555] mx-auto" />
              <p className="text-[11px] text-[#555]">Loading PDF...</p>
            </div>
          </div>
        ) : activeUrl ? (
          <iframe
            key={pdfView}
            src={activeUrl}
            className="absolute inset-0 w-full h-full border-0"
            title={
              pdfView === "diff"
                ? "Resume Diff"
                : "Tailored Resume"
            }
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-[12px] text-[#555]">
            PDF not available
          </div>
        )}
      </div>

      {/* Optimized sections footer */}
      {data.sections_optimized && data.sections_optimized.length > 0 && (
        <div className="px-4 py-2 border-t border-[#222] flex flex-wrap gap-1.5 shrink-0">
          <span className="text-[10px] text-[#555] mr-1">Optimized:</span>
          {data.sections_optimized.map((s) => (
            <span
              key={s}
              className="px-2 py-0.5 rounded bg-[#1a1a1a] text-[#888] text-[10px]"
            >
              {s}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
