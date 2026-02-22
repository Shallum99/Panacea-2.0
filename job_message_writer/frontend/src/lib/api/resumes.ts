import api from "@/lib/api";

export interface ExtractedInfo {
  name: string;
  email: string;
  phone: string;
  skills: string[];
  years_experience: string;
  education: string;
  recent_job: string;
  recent_company: string;
}

export interface ProfileClassification {
  profile_type: string;
  primary_languages: string[];
  frameworks: string[];
  years_experience: string;
  seniority: string;
  industry_focus: string;
}

export interface Resume {
  id: number;
  title: string;
  filename: string;
  is_active: boolean;
  extracted_info: ExtractedInfo;
  profile_classification: ProfileClassification;
}

export interface ResumeWithContent extends Resume {
  content: string;
}

export async function uploadResume(
  file: File,
  title: string,
  makeActive: boolean = true
): Promise<Resume> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("title", title);
  formData.append("make_active", makeActive.toString());

  const { data } = await api.post("/resumes/", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function getResumes(): Promise<Resume[]> {
  const { data } = await api.get("/resumes/");
  return data;
}

export async function getResume(id: number): Promise<Resume> {
  const { data } = await api.get(`/resumes/${id}`);
  return data;
}

export async function getActiveResume(): Promise<Resume> {
  const { data } = await api.get("/resumes/active");
  return data;
}

export async function setActiveResume(id: number): Promise<Resume> {
  const { data } = await api.post(`/resumes/${id}/set-active`);
  return data;
}

export async function getResumeContent(id: number): Promise<ResumeWithContent> {
  const { data } = await api.get(`/resumes/${id}/content`);
  return data;
}

export function getResumePdfUrl(id: number): string {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
  return `${base}/resumes/${id}/pdf`;
}

export async function deleteResume(id: number): Promise<void> {
  await api.delete(`/resumes/${id}`);
}

// ── Resume Editor Types & API ────────────────────────────────────────

export interface FormMapField {
  id: string;
  type: "bullet" | "skill" | "title";
  section: string | null;
  text: string;
  label: string | null;
  max_chars: number | null;
  line_count: number | null;
  char_per_line: number[] | null;
  protected: boolean;
}

export interface FormMapResponse {
  fields: FormMapField[];
  editable_fields: number;
  font_quality: string;
  font_coverage_pct: number;
  resume_id: number;
}

export interface EditChange {
  field_id: string;
  field_type: string;
  section: string | null;
  original_text: string;
  new_text: string;
  reasoning: string | null;
  warnings: string[] | null;
}

export interface EditResponse {
  version_number: number;
  download_id: string;
  diff_download_id: string | null;
  changes: EditChange[];
  prompt_used: string;
}

export interface VersionSummary {
  version_number: number;
  download_id: string;
  diff_download_id: string | null;
  prompt_used: string;
  change_count: number;
  created_at: string;
}

export interface VersionListResponse {
  versions: VersionSummary[];
  total: number;
}

export async function getFormMap(
  resumeId: number,
  refresh = false
): Promise<FormMapResponse> {
  const { data } = await api.get(
    `/resume-editor/${resumeId}/form-map`,
    { params: refresh ? { refresh: true } : {} }
  );
  return data;
}

export async function editResume(
  resumeId: number,
  prompt: string,
  fieldTargets?: string[],
  sourceVersion?: number
): Promise<EditResponse> {
  const { data } = await api.post(`/resume-editor/${resumeId}/edit`, {
    prompt,
    field_targets: fieldTargets ?? null,
    source_version: sourceVersion ?? null,
  });
  return data;
}

export async function getResumeVersions(
  resumeId: number
): Promise<VersionListResponse> {
  const { data } = await api.get(`/resume-editor/${resumeId}/versions`);
  return data;
}

export function getEditorDownloadUrl(
  resumeId: number,
  downloadId: string
): string {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
  return `${base}/resume-editor/${resumeId}/download/${downloadId}`;
}
