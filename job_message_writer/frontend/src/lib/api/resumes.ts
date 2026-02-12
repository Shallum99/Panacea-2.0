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
