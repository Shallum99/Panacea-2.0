import api from "@/lib/api";

export interface Application {
  id: number;
  status: string;
  method: string;
  company_name: string | null;
  position_title: string | null;
  recipient_email: string | null;
  recipient_name: string | null;
  job_url: string | null;
  message_type: string | null;
  generated_message: string | null;
  edited_message: string | null;
  final_message: string | null;
  resume_id: number | null;
  job_description_id: number | null;
  ats_score_before: number | null;
  ats_score_after: number | null;
  email_message_id: string | null;
  sent_at: string | null;
  opened_at: string | null;
  replied_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CreateApplicationRequest {
  job_description: string;
  message_type?: string;
  resume_id?: number;
  recruiter_name?: string;
  recipient_email?: string;
  job_url?: string;
  position_title?: string;
}

export interface UpdateApplicationRequest {
  edited_message?: string;
  recipient_email?: string;
  recipient_name?: string;
  status?: string;
}

export async function createApplication(
  data: CreateApplicationRequest
): Promise<Application> {
  const { data: result } = await api.post("/applications/", data);
  return result;
}

export async function getApplications(
  status?: string
): Promise<Application[]> {
  const params = status ? { status } : {};
  const { data } = await api.get("/applications/", { params });
  return data;
}

export async function getApplication(id: number): Promise<Application> {
  const { data } = await api.get(`/applications/${id}`);
  return data;
}

export async function updateApplication(
  id: number,
  data: UpdateApplicationRequest
): Promise<Application> {
  const { data: result } = await api.patch(`/applications/${id}`, data);
  return result;
}

export async function approveApplication(id: number): Promise<Application> {
  const { data } = await api.post(`/applications/${id}/approve`);
  return data;
}

export async function sendApplication(id: number): Promise<Application> {
  const { data } = await api.post(`/applications/${id}/send`);
  return data;
}

export async function deleteApplication(id: number): Promise<void> {
  await api.delete(`/applications/${id}`);
}
