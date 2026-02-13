"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  type Conversation,
  type ChatContext,
  type ChatEvent,
  listConversations,
  getConversation,
  deleteConversation as apiDeleteConversation,
  createConversationWithContext,
  sendMessageWithContext,
} from "@/lib/api/chat";
import { getResumes } from "@/lib/api/resumes";

export interface DisplayMessage {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  toolName?: string;
  richType?: string;
  richData?: unknown;
}

interface ResumeOption {
  id: number;
  title: string;
  is_active: boolean;
}

const CONTEXT_STORAGE_KEY = "agentic-apply-context";

export function useAgenticChat(searchParams?: URLSearchParams) {
  // Conversation state
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationsLoading, setConversationsLoading] = useState(true);

  // Chat state
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  // Context state
  const [context, setContextState] = useState<ChatContext>({});
  const [contextModalOpen, setContextModalOpen] = useState(false);
  const [resumes, setResumes] = useState<ResumeOption[]>([]);

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);

  // Load conversations on mount
  useEffect(() => {
    loadConversations();
    loadResumes();
    loadContextFromStorage();
  }, []);

  // Handle URL params
  useEffect(() => {
    if (!searchParams) return;
    const convId = searchParams.get("conversation");
    if (convId) {
      selectConversation(Number(convId));
    }
  }, [searchParams]);

  // Auto-scroll
  useEffect(() => {
    if (autoScrollRef.current && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  async function loadConversations() {
    try {
      setConversationsLoading(true);
      const convs = await listConversations();
      setConversations(convs);
    } catch {
      // silent fail
    } finally {
      setConversationsLoading(false);
    }
  }

  async function loadResumes() {
    try {
      const data = await getResumes();
      setResumes(
        data.map((r: { id: number; title: string; is_active: boolean }) => ({
          id: r.id,
          title: r.title,
          is_active: r.is_active,
        }))
      );
    } catch {
      // silent fail
    }
  }

  function loadContextFromStorage() {
    try {
      const stored = sessionStorage.getItem(CONTEXT_STORAGE_KEY);
      if (stored) {
        setContextState(JSON.parse(stored));
      }
    } catch {
      // ignore
    }
  }

  const setContext = useCallback((ctx: ChatContext) => {
    setContextState(ctx);
    try {
      sessionStorage.setItem(CONTEXT_STORAGE_KEY, JSON.stringify(ctx));
    } catch {
      // ignore
    }
  }, []);

  const selectConversation = useCallback(async (id: number) => {
    setConversationId(id);
    try {
      const detail = await getConversation(id);
      const displayMessages: DisplayMessage[] = [];

      for (const msg of detail.messages) {
        if (msg.role === "user") {
          displayMessages.push({
            id: String(msg.id),
            role: "user",
            content: msg.content,
          });
        } else if (msg.role === "assistant") {
          displayMessages.push({
            id: String(msg.id),
            role: "assistant",
            content: msg.content,
          });
        } else if (msg.role === "tool_result") {
          let richData: unknown = {};
          try {
            richData = JSON.parse(msg.content);
          } catch {
            richData = { raw: msg.content };
          }
          const richType = inferRichType(msg.tool_name);
          displayMessages.push({
            id: String(msg.id),
            role: "tool",
            content: "",
            toolName: msg.tool_name || undefined,
            richType,
            richData,
          });
        }
      }

      setMessages(displayMessages);
    } catch {
      setMessages([]);
    }
  }, []);

  const newConversation = useCallback(() => {
    setConversationId(null);
    setMessages([]);
    setInput("");
    setContextState({});
    try {
      sessionStorage.removeItem(CONTEXT_STORAGE_KEY);
    } catch {
      // ignore
    }
  }, []);

  const handleDeleteConversation = useCallback(
    async (id: number) => {
      try {
        await apiDeleteConversation(id);
        setConversations((prev) => prev.filter((c) => c.id !== id));
        if (conversationId === id) {
          newConversation();
        }
      } catch {
        // silent fail
      }
    },
    [conversationId, newConversation]
  );

  const sendMessage = useCallback(
    async (text?: string) => {
      const msg = (text || input).trim();
      if (!msg || sending) return;

      setSending(true);
      setInput("");
      autoScrollRef.current = true;

      // Add user message immediately
      const userMsgId = `user-${Date.now()}`;
      setMessages((prev) => [
        ...prev,
        { id: userMsgId, role: "user", content: msg },
      ]);

      try {
        // Create conversation if needed
        let convId = conversationId;
        if (!convId) {
          const conv = await createConversationWithContext(context);
          convId = conv.id;
          setConversationId(convId);
          setConversations((prev) => [conv, ...prev]);
        }

        // Stream response
        let assistantMsgId = "";
        await sendMessageWithContext(convId, msg, context, (event: ChatEvent) => {
          switch (event.type) {
            case "tool_start": {
              const toolMsgId = `tool-start-${Date.now()}-${event.tool}`;
              setMessages((prev) => [
                ...prev,
                {
                  id: toolMsgId,
                  role: "tool",
                  content: "",
                  toolName: event.tool,
                  richType: "tool_loading",
                  richData: { tool: event.tool, args: event.args },
                },
              ]);
              break;
            }
            case "tool_result": {
              // Remove the loading indicator for this tool
              setMessages((prev) => {
                const filtered = prev.filter(
                  (m) =>
                    !(
                      m.richType === "tool_loading" &&
                      m.toolName === event.tool
                    )
                );
                return [
                  ...filtered,
                  {
                    id: `tool-result-${Date.now()}-${event.tool}`,
                    role: "tool",
                    content: "",
                    toolName: event.tool,
                    richType: event.rich_type,
                    richData: event.result,
                  },
                ];
              });

              // If this is a context update from set_context tool, merge into context state
              if (event.rich_type === "context_update" && event.result) {
                const update = event.result as Partial<ChatContext>;
                setContextState((prev) => {
                  const merged = { ...prev, ...update };
                  try {
                    sessionStorage.setItem(CONTEXT_STORAGE_KEY, JSON.stringify(merged));
                  } catch { /* ignore */ }
                  return merged;
                });
              }
              break;
            }
            case "text": {
              if (!assistantMsgId) {
                assistantMsgId = `assistant-${Date.now()}`;
                setMessages((prev) => [
                  ...prev,
                  {
                    id: assistantMsgId,
                    role: "assistant",
                    content: event.content,
                  },
                ]);
              } else {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId
                      ? { ...m, content: m.content + event.content }
                      : m
                  )
                );
              }
              break;
            }
            case "done":
              break;
          }
        });

        // Refresh conversation list to update title/timestamp
        loadConversations();
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: "assistant",
            content:
              "Something went wrong. Please try again.",
          },
        ]);
      } finally {
        setSending(false);
      }
    },
    [input, sending, conversationId, context]
  );

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    autoScrollRef.current = isAtBottom;
  }, []);

  return {
    // Conversations
    conversations,
    conversationsLoading,
    conversationId,
    selectConversation,
    newConversation,
    deleteConversation: handleDeleteConversation,

    // Messages
    messages,
    input,
    setInput,
    sending,
    sendMessage,

    // Context
    context,
    setContext,
    contextModalOpen,
    setContextModalOpen,
    resumes,

    // Scroll
    messagesEndRef,
    handleScroll,

    // Actions
    refreshResumes: loadResumes,
  };
}

function inferRichType(toolName: string | null): string {
  const map: Record<string, string> = {
    search_jobs: "job_cards",
    get_job_detail: "job_detail",
    import_job_url: "job_detail",
    generate_message: "message_preview",
    iterate_message: "message_preview",
    tailor_resume: "resume_tailored",
    get_ats_score: "resume_score",
    send_email: "email_sent",
    list_applications: "applications_list",
    list_resumes: "resumes_list",
    save_job: "job_saved",
    research_company: "company_research",
    set_context: "context_update",
    edit_tailored_resume: "resume_tailored",
  };
  return map[toolName || ""] || "generic";
}
