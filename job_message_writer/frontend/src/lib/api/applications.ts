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

/**
 * Stream message generation via SSE.
 * Tokens arrive in real-time, then final application data on completion.
 */
export async function streamApplication(
  data: CreateApplicationRequest,
  onToken: (text: string) => void,
  onDone: (app: Application) => void,
  onError: (error: string) => void,
  getToken: () => Promise<string | null>,
): Promise<void> {
  const token = await getToken();
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

  const response = await fetch(`${baseUrl}/applications/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const err = await response.text();
    throw new Error(err || `HTTP ${response.status}`);
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const event = JSON.parse(line.slice(6));
        if (event.type === "token") {
          onToken(event.text);
        } else if (event.type === "done") {
          onDone(event.application as Application);
        } else if (event.type === "error") {
          onError(event.detail || "Stream error");
        }
      } catch {
        // skip malformed lines
      }
    }
  }
}
