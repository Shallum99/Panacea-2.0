import api from "@/lib/api";
import { createClient } from "@/lib/supabase/client";

export interface Conversation {
  id: number;
  title: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface ChatMessage {
  id: number;
  role: string;
  content: string;
  tool_name: string | null;
  tool_call_id: string | null;
  created_at: string | null;
}

export interface ConversationWithMessages extends Conversation {
  messages: ChatMessage[];
}

export type ChatEvent =
  | { type: "tool_start"; tool: string; args: Record<string, unknown> }
  | { type: "tool_result"; tool: string; result: unknown; rich_type: string }
  | { type: "text"; content: string }
  | { type: "done" };

export async function createConversation(): Promise<Conversation> {
  const { data } = await api.post("/chat/conversations");
  return data;
}

export async function listConversations(): Promise<Conversation[]> {
  const { data } = await api.get("/chat/conversations");
  return data;
}

export async function getConversation(
  id: number
): Promise<ConversationWithMessages> {
  const { data } = await api.get(`/chat/conversations/${id}`);
  return data;
}

export async function deleteConversation(id: number): Promise<void> {
  await api.delete(`/chat/conversations/${id}`);
}

export interface ChatContext {
  job_description?: string;
  resume_id?: number;
  message_type?: string;
  position_title?: string;
  recruiter_name?: string;
}

export async function createConversationWithContext(
  context?: ChatContext
): Promise<Conversation> {
  const body: Record<string, unknown> = {};
  if (context?.position_title) {
    body.title = context.position_title;
    body.context = context;
  }
  const { data } = await api.post("/chat/conversations", body);
  return data;
}

export async function sendMessageWithContext(
  conversationId: number,
  message: string,
  context: ChatContext | null,
  onEvent: (event: ChatEvent) => void
): Promise<void> {
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

  const response = await fetch(
    `${baseUrl}/chat/conversations/${conversationId}/send`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ message, context }),
    }
  );

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
        const event = JSON.parse(line.slice(6)) as ChatEvent;
        onEvent(event);
      } catch {
        // skip malformed lines
      }
    }
  }
}

export async function sendMessage(
  conversationId: number,
  message: string,
  onEvent: (event: ChatEvent) => void
): Promise<void> {
  const baseUrl =
    process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

  // Get auth token
  let token: string | null = null;
  if (process.env.NEXT_PUBLIC_DEV_MODE !== "true") {
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    token = session?.access_token ?? null;
  }

  const response = await fetch(
    `${baseUrl}/chat/conversations/${conversationId}/send`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ message }),
    }
  );

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
        const event = JSON.parse(line.slice(6)) as ChatEvent;
        onEvent(event);
      } catch {
        // skip malformed lines
      }
    }
  }
}
