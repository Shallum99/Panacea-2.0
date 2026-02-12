"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  X,
  Send,
  Plus,
  Trash2,
  MessageSquare,
  Loader2,
  ChevronDown,
} from "lucide-react";
import {
  createConversation,
  listConversations,
  getConversation,
  deleteConversation,
  sendMessage,
  type Conversation,
  type ChatMessage as ChatMessageType,
  type ChatEvent,
} from "@/lib/api/chat";
import ChatRichResult from "./ChatRichResults";

interface Props {
  open: boolean;
  onClose: () => void;
}

interface DisplayMessage {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  toolName?: string;
  richType?: string;
  richData?: unknown;
}

export default function ChatPanel({ open, onClose }: Props) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<number | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [showConvPicker, setShowConvPicker] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Listen for toggle-chat event
  useEffect(() => {
    function handleToggle() {
      if (open) onClose();
    }
    document.addEventListener("toggle-chat", handleToggle);
    return () => document.removeEventListener("toggle-chat", handleToggle);
  }, [open, onClose]);

  // Load conversations when panel opens
  useEffect(() => {
    if (open) {
      loadConversations();
      setTimeout(() => inputRef.current?.focus(), 300);
    }
  }, [open]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function loadConversations() {
    try {
      const convs = await listConversations();
      setConversations(convs);
      if (convs.length > 0 && !activeConvId) {
        await loadConversation(convs[0].id);
      }
    } catch {
      // ignore
    }
  }

  async function loadConversation(id: number) {
    try {
      const conv = await getConversation(id);
      setActiveConvId(id);
      setMessages(dbMessagesToDisplay(conv.messages));
      setShowConvPicker(false);
    } catch {
      // ignore
    }
  }

  function dbMessagesToDisplay(dbMessages: ChatMessageType[]): DisplayMessage[] {
    const display: DisplayMessage[] = [];
    for (const msg of dbMessages) {
      if (msg.role === "user") {
        display.push({ id: `db-${msg.id}`, role: "user", content: msg.content });
      } else if (msg.role === "assistant") {
        display.push({ id: `db-${msg.id}`, role: "assistant", content: msg.content });
      } else if (msg.role === "tool_result") {
        try {
          const data = JSON.parse(msg.content);
          display.push({
            id: `db-${msg.id}`,
            role: "tool",
            content: "",
            toolName: msg.tool_name || undefined,
            richType: inferRichType(msg.tool_name),
            richData: data,
          });
        } catch {
          // skip
        }
      }
      // tool_use messages are not displayed (we show tool_start during streaming)
    }
    return display;
  }

  function inferRichType(toolName: string | null): string {
    const map: Record<string, string> = {
      search_jobs: "job_cards",
      get_job_detail: "job_detail",
      import_job_url: "job_detail",
      list_resumes: "resumes_list",
      generate_message: "message_preview",
      tailor_resume: "resume_tailored",
      get_ats_score: "resume_score",
      send_email: "email_sent",
      list_applications: "applications_list",
      save_job: "job_saved",
    };
    return map[toolName || ""] || "generic";
  }

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;

    setSending(true);
    setInput("");

    // Create conversation if needed
    let convId = activeConvId;
    if (!convId) {
      try {
        const conv = await createConversation();
        convId = conv.id;
        setActiveConvId(conv.id);
        setConversations((prev) => [conv, ...prev]);
      } catch {
        setSending(false);
        return;
      }
    }

    // Add user message
    const userMsgId = `user-${Date.now()}`;
    setMessages((prev) => [...prev, { id: userMsgId, role: "user", content: text }]);

    // Stream assistant response
    let assistantText = "";
    const assistantMsgId = `assistant-${Date.now()}`;

    try {
      await sendMessage(convId, text, (event: ChatEvent) => {
        switch (event.type) {
          case "tool_start":
            setMessages((prev) => [
              ...prev,
              {
                id: `tool-start-${Date.now()}-${Math.random()}`,
                role: "tool",
                content: `Using ${formatToolName(event.tool)}...`,
                toolName: event.tool,
              },
            ]);
            break;

          case "tool_result":
            // Replace the tool_start with the result
            setMessages((prev) => {
              const updated = [...prev];
              // Find the last tool message for this tool
              for (let i = updated.length - 1; i >= 0; i--) {
                if (updated[i].toolName === event.tool && !updated[i].richData) {
                  updated[i] = {
                    ...updated[i],
                    content: "",
                    richType: event.rich_type,
                    richData: event.result,
                  };
                  break;
                }
              }
              return updated;
            });
            break;

          case "text":
            assistantText += event.content;
            setMessages((prev) => {
              const existing = prev.find((m) => m.id === assistantMsgId);
              if (existing) {
                return prev.map((m) =>
                  m.id === assistantMsgId ? { ...m, content: assistantText } : m
                );
              }
              return [
                ...prev,
                { id: assistantMsgId, role: "assistant", content: assistantText },
              ];
            });
            break;

          case "done":
            break;
        }
      });
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          content: `Error: ${err instanceof Error ? err.message : "Something went wrong"}`,
        },
      ]);
    }

    // Refresh conversation list
    loadConversations();
    setSending(false);
  }, [input, sending, activeConvId]);

  async function handleNewChat() {
    try {
      const conv = await createConversation();
      setActiveConvId(conv.id);
      setConversations((prev) => [conv, ...prev]);
      setMessages([]);
      setShowConvPicker(false);
    } catch {
      // ignore
    }
  }

  async function handleDeleteConversation(id: number, e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeConvId === id) {
        setActiveConvId(null);
        setMessages([]);
      }
    } catch {
      // ignore
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function formatToolName(name: string): string {
    return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40 bg-black/20"
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            className="fixed right-0 top-0 bottom-0 z-40 w-[480px] max-w-[90vw] bg-background border-l border-border flex flex-col shadow-2xl"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 h-14 border-b border-border shrink-0">
              <div className="flex items-center gap-2">
                <MessageSquare size={16} className="text-accent" />
                <button
                  onClick={() => setShowConvPicker(!showConvPicker)}
                  className="flex items-center gap-1 text-sm font-medium hover:text-accent transition-colors"
                >
                  {conversations.find((c) => c.id === activeConvId)?.title ||
                    "New Chat"}
                  <ChevronDown size={14} />
                </button>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={handleNewChat}
                  className="w-8 h-8 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  title="New chat"
                >
                  <Plus size={16} />
                </button>
                <button
                  onClick={onClose}
                  className="w-8 h-8 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Conversation picker dropdown */}
            {showConvPicker && (
              <div className="absolute top-14 left-0 right-0 z-10 bg-card border-b border-border max-h-60 overflow-y-auto shadow-lg">
                {conversations.map((conv) => (
                  <div
                    key={conv.id}
                    onClick={() => loadConversation(conv.id)}
                    className={`flex items-center justify-between px-4 py-2.5 text-sm cursor-pointer hover:bg-muted transition-colors ${
                      conv.id === activeConvId ? "bg-accent/10 text-accent" : ""
                    }`}
                  >
                    <span className="truncate">{conv.title}</span>
                    <button
                      onClick={(e) => handleDeleteConversation(conv.id, e)}
                      className="text-muted-foreground hover:text-destructive shrink-0 ml-2"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}
                {conversations.length === 0 && (
                  <div className="px-4 py-3 text-sm text-muted-foreground">
                    No conversations yet
                  </div>
                )}
              </div>
            )}

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
              {messages.length === 0 && (
                <div className="flex flex-col items-center justify-center h-full text-center">
                  <MessageSquare
                    size={40}
                    className="text-muted-foreground/30 mb-3"
                  />
                  <p className="text-sm font-medium text-muted-foreground">
                    How can I help?
                  </p>
                  <p className="text-xs text-muted-foreground/70 mt-1 max-w-[240px]">
                    Search for jobs, generate messages, tailor your resume, or
                    check application status.
                  </p>
                  <div className="mt-4 space-y-1.5">
                    {[
                      "Find backend engineer jobs at Stripe",
                      "Generate a cover letter for this role",
                      "What's the ATS score of my resume?",
                    ].map((suggestion) => (
                      <button
                        key={suggestion}
                        onClick={() => {
                          setInput(suggestion);
                          setTimeout(() => inputRef.current?.focus(), 0);
                        }}
                        className="block w-full text-left text-xs px-3 py-2 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:border-accent/30 transition-colors"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((msg) => (
                <div key={msg.id}>
                  {msg.role === "user" ? (
                    <div className="flex justify-end">
                      <div className="max-w-[85%] px-3.5 py-2.5 rounded-2xl rounded-br-md bg-accent text-accent-foreground text-sm whitespace-pre-wrap">
                        {msg.content}
                      </div>
                    </div>
                  ) : msg.role === "tool" ? (
                    <div className="max-w-[95%]">
                      {msg.richData ? (
                        <ChatRichResult
                          richType={msg.richType || "generic"}
                          data={msg.richData}
                        />
                      ) : (
                        <div className="flex items-center gap-2 text-xs text-muted-foreground py-1.5">
                          <Loader2 size={12} className="animate-spin" />
                          <span>{msg.content}</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="max-w-[85%]">
                      <div className="px-3.5 py-2.5 rounded-2xl rounded-bl-md bg-card border border-border text-sm whitespace-pre-wrap">
                        {msg.content}
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {sending && messages[messages.length - 1]?.role === "user" && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground py-1">
                  <Loader2 size={12} className="animate-spin" />
                  <span>Thinking...</span>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="border-t border-border p-3 shrink-0">
              <div className="flex items-end gap-2 bg-card border border-border rounded-xl px-3 py-2">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask anything..."
                  rows={1}
                  className="flex-1 bg-transparent text-sm resize-none outline-none placeholder:text-muted-foreground max-h-32"
                  style={{
                    height: "auto",
                    minHeight: "24px",
                  }}
                  onInput={(e) => {
                    const el = e.target as HTMLTextAreaElement;
                    el.style.height = "auto";
                    el.style.height = Math.min(el.scrollHeight, 128) + "px";
                  }}
                />
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || sending}
                  className="w-8 h-8 flex items-center justify-center rounded-lg bg-accent text-accent-foreground disabled:opacity-30 transition-opacity shrink-0"
                >
                  <Send size={14} />
                </button>
              </div>
              <p className="text-[10px] text-muted-foreground/50 mt-1.5 text-center">
                Press Enter to send, Shift+Enter for new line
              </p>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
