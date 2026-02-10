import api from "@/lib/api";

export interface AutoApplyStep {
  name: string;
  status: string;
  screenshot_path: string | null;
  detail: string;
  timestamp: string | null;
}

export interface AutoApplyStatus {
  task_id: string;
  job_url: string;
  status: string;
  steps: AutoApplyStep[];
  error: string | null;
}

export interface EmailAutoApplyRequest {
  job_description: string;
  recipient_email: string;
  resume_id?: number;
  position_title?: string;
  recruiter_name?: string;
  optimize_resume?: boolean;
}

export interface EmailAutoApplyResponse {
  status: string;
  application_id: number;
  company_name: string;
  message_preview: string;
  email_message_id: string | null;
  resume_optimized: boolean;
}

export interface URLAutoApplyRequest {
  job_url: string;
  resume_id?: number;
  cover_letter?: string;
}

export async function emailAutoApply(
  data: EmailAutoApplyRequest
): Promise<EmailAutoApplyResponse> {
  const { data: result } = await api.post("/auto-apply/email", data);
  return result;
}

export async function urlAutoApply(
  data: URLAutoApplyRequest
): Promise<AutoApplyStatus> {
  const { data: result } = await api.post("/auto-apply/url", data);
  return result;
}

export async function getAutoApplyStatus(
  taskId: string
): Promise<AutoApplyStatus> {
  const { data } = await api.get(`/auto-apply/status/${taskId}`);
  return data;
}

export async function cancelAutoApply(taskId: string): Promise<void> {
  await api.post(`/auto-apply/cancel/${taskId}`);
}

export async function submitAutoApply(
  taskId: string
): Promise<AutoApplyStatus> {
  const { data } = await api.post(`/auto-apply/submit/${taskId}`);
  return data;
}

export function getScreenshotUrl(filename: string): string {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
  return `${base}/auto-apply/screenshot/${filename}`;
}

export function getWebSocketUrl(taskId: string): string {
  const base = (
    process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api"
  ).replace("http", "ws");
  return `${base}/auto-apply/ws/${taskId}`;
}
