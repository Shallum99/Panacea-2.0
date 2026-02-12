import api from "@/lib/api";

export interface JobSearchResult {
  id: string;
  title: string;
  company: string;
  location: string | null;
  department: string | null;
  url: string;
  source: "greenhouse" | "lever";
  updated_at: string | null;
  workplace_type: string | null;
  salary_range: string | null;
}

export interface JobSearchResponse {
  results: JobSearchResult[];
  total: number;
}

export interface JobDetail {
  id: string;
  title: string;
  company: string;
  location: string | null;
  department: string | null;
  content: string;
  url: string;
  source: string;
  apply_url: string | null;
  salary_range: string | null;
  workplace_type: string | null;
}

export interface SavedJob {
  id: number;
  title: string;
  content: string;
  company_info: Record<string, unknown> | null;
  url: string | null;
  source: string | null;
}

export async function searchJobs(params: {
  q?: string;
  company?: string;
  location?: string;
  source?: string;
}): Promise<JobSearchResponse> {
  const { data } = await api.get("/jobs/search", { params });
  return data;
}

export async function getJobDetail(
  source: string,
  company: string,
  jobId: string
): Promise<JobDetail> {
  const { data } = await api.get(
    `/jobs/detail/${source}/${company}/${jobId}`
  );
  return data;
}

export async function createJdFromUrl(url: string): Promise<SavedJob> {
  const { data } = await api.post("/job-descriptions/from-url", { url });
  return data;
}

export async function getSavedJobs(): Promise<SavedJob[]> {
  const { data } = await api.get("/job-descriptions/");
  return data;
}
