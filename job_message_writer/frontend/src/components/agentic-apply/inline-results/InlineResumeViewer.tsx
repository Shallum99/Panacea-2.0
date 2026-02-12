"use client";

import { useState, useEffect } from "react";
import { Download, Maximize2, FileText } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

interface TailorData {
  resume_title?: string;
  download_id?: string;
  sections_optimized?: string[];
  ats_score_before?: number;
  ats_score_after?: number;
}

interface Props {
  data: TailorData;
}

export default function InlineResumeViewer({ data }: Props) {
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!data.download_id) return;
    loadPdf();
    return () => {
      if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    };
  }, [data.download_id]);

  async function loadPdf() {
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
        `${baseUrl}/resume-tailor/download/${data.download_id}`,
        {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        }
      );
      if (!res.ok) return;
      const blob = await res.blob();
      setPdfUrl(URL.createObjectURL(blob));
    } catch {
      // silent
    }
  }

  const scoreDelta =
    data.ats_score_after != null && data.ats_score_before != null
      ? data.ats_score_after - data.ats_score_before
      : null;

  return (
    <div className="border-l-2 border-success/40 rounded-xl bg-card/60 overflow-hidden ml-10">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/50">
        <div className="flex items-center gap-2">
          <FileText size={13} className="text-success" />
          <span className="text-[12px] font-medium">
            Tailored: {data.resume_title}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {pdfUrl && (
            <>
              <a
                href={pdfUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-foreground/[0.05] transition-colors"
                title="View Full Screen"
              >
                <Maximize2 size={12} />
              </a>
              <a
                href={pdfUrl}
                download={`tailored-${data.resume_title}.pdf`}
                className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-foreground/[0.05] transition-colors"
                title="Download"
              >
                <Download size={12} />
              </a>
            </>
          )}
        </div>
      </div>

      {/* Score */}
      {data.ats_score_before != null && data.ats_score_after != null && (
        <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border/50">
          <span className="text-[12px] text-muted-foreground">
            ATS: {data.ats_score_before}%
          </span>
          <span className="text-accent text-[12px]">&rarr;</span>
          <span className="text-[12px] font-medium text-success">
            {data.ats_score_after}%
          </span>
          {scoreDelta != null && scoreDelta > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-success/10 text-success">
              +{scoreDelta}%
            </span>
          )}
        </div>
      )}

      {/* PDF Preview */}
      {pdfUrl ? (
        <div className="p-3">
          <iframe
            src={pdfUrl}
            className="w-full rounded-lg border border-border"
            style={{ height: 480 }}
            title="Tailored Resume PDF"
          />
        </div>
      ) : (
        <div className="flex items-center justify-center py-16 text-[12px] text-muted-foreground/50">
          Loading PDF...
        </div>
      )}

      {/* Sections optimized */}
      {data.sections_optimized && data.sections_optimized.length > 0 && (
        <div className="px-4 py-2.5 border-t border-border/50 flex flex-wrap gap-1.5">
          <span className="text-[10px] text-muted-foreground/50 mr-1">
            Optimized:
          </span>
          {data.sections_optimized.map((s) => (
            <span
              key={s}
              className="px-2 py-0.5 rounded-full bg-success/10 text-success text-[10px]"
            >
              {s}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
