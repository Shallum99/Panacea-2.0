import api from "@/lib/api";

export interface SectionInfo {
  name: string;
  content_text: string;
  num_content_lines: number;
  char_count: number;
}

export interface SectionMapResponse {
  total_spans: number;
  total_lines: number;
  sections: SectionInfo[];
}

export interface TextChange {
  section: string;
  type: string;
  original: string;
  optimized: string;
}

export interface PDFOptimizeResponse {
  download_id: string;
  sections_found: string[];
  sections_optimized: string[];
  original_ats_score: number;
  optimized_ats_score: number;
  changes: TextChange[];
}

export interface ATSScoreResponse {
  score: number;
  breakdown: Record<string, number>;
  suggestions: string[];
}

export async function getSectionMap(
  jobDescription: string,
  resumeId?: number
): Promise<SectionMapResponse> {
  const { data } = await api.post("/resume-tailor/section-map", {
    job_description: jobDescription,
    resume_id: resumeId,
  });
  return data;
}

export async function optimizePDF(
  jobDescription: string,
  resumeId?: number
): Promise<PDFOptimizeResponse> {
  const { data } = await api.post("/resume-tailor/optimize-pdf", {
    job_description: jobDescription,
    resume_id: resumeId,
  });
  return data;
}

export function getDownloadUrl(downloadId: string): string {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
  return `${base}/resume-tailor/download/${downloadId}`;
}

export async function getATSScore(
  resumeContent: string,
  jobDescription: string
): Promise<ATSScoreResponse> {
  const { data } = await api.post("/resume-tailor/score", {
    resume_content: resumeContent,
    job_description: jobDescription,
  });
  return data;
}
