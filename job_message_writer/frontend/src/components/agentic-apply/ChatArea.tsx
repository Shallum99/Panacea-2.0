"use client";

import { useRef, useEffect } from "react";
import { Sparkles, ArrowUp, Loader2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import type { DisplayMessage } from "@/hooks/useAgenticChat";
import type { ChatContext } from "@/lib/api/chat";
import InlineRichResult from "./inline-results";

interface Props {
  messages: DisplayMessage[];
  input: string;
  setInput: (v: string) => void;
  sending: boolean;
  sendMessage: (text?: string) => void;
  context: ChatContext;
  onScroll: (e: React.UIEvent<HTMLDivElement>) => void;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  onOpenContext: () => void;
}

const TOOL_LABELS: Record<string, string> = {
  search_jobs: "Searching jobs",
  get_job_detail: "Fetching job details",
  import_job_url: "Importing from URL",
  list_resumes: "Loading resumes",
  generate_message: "Generating message",
  iterate_message: "Revising message",
  tailor_resume: "Tailoring resume",
  get_ats_score: "Scoring resume",
  send_email: "Sending email",
  list_applications: "Loading applications",
  save_job: "Saving job",
};

const SUGGESTIONS = [
  "Generate a cover letter",
  "Tailor my resume for this role",
  "Check my ATS compatibility score",
  "Help me prepare for the interview",
];

function hasContext(ctx: ChatContext): boolean {
  return !!(ctx.job_description || ctx.resume_id || ctx.position_title);
}

export default function ChatArea({
  messages,
  input,
  setInput,
  sending,
  sendMessage,
  context,
  onScroll,
  messagesEndRef,
  onOpenContext,
}: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 160) + "px";
    }
  }, [input]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  const showWelcome = messages.length === 0;
  const contextReady = hasContext(context);

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div
        className="flex-1 overflow-y-auto px-4 py-6"
        onScroll={onScroll}
      >
        {showWelcome ? (
          <div className="flex flex-col items-center justify-center h-full max-w-md mx-auto text-center">
            <div className="w-12 h-12 rounded-2xl bg-accent/10 flex items-center justify-center mb-4">
              <Sparkles size={22} className="text-accent" />
            </div>
            <h2 className="text-lg font-semibold mb-1">Panacea</h2>
            {contextReady ? (
              <>
                <p className="text-[13px] text-muted-foreground mb-6">
                  Your context is set. What would you like to do?
                </p>
                <div className="grid grid-cols-2 gap-2 w-full">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => sendMessage(s)}
                      className="px-3 py-2.5 rounded-xl text-[12px] text-left text-muted-foreground border border-border hover:border-accent/30 hover:text-foreground hover:bg-foreground/[0.02] transition-all duration-200"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <>
                <p className="text-[13px] text-muted-foreground mb-4">
                  Set your application context to get started
                </p>
                <button
                  onClick={onOpenContext}
                  className="btn-gradient px-4 py-2 text-[13px]"
                >
                  Set Context
                </button>
              </>
            )}
          </div>
        ) : (
          <div className="max-w-2xl mx-auto space-y-4">
            <AnimatePresence initial={false}>
              {messages.map((msg) => (
                <motion.div
                  key={msg.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25 }}
                >
                  {msg.role === "user" ? (
                    <UserBubble content={msg.content} />
                  ) : msg.role === "tool" ? (
                    msg.richType === "tool_loading" ? (
                      <ToolLoadingIndicator toolName={msg.toolName || ""} />
                    ) : (
                      <InlineRichResult
                        richType={msg.richType || "generic"}
                        data={msg.richData}
                        onSendMessage={sendMessage}
                      />
                    )
                  ) : (
                    <AssistantBubble content={msg.content} />
                  )}
                </motion.div>
              ))}
            </AnimatePresence>
            {sending && messages[messages.length - 1]?.role !== "tool" && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex items-start gap-3"
              >
                <div className="w-7 h-7 rounded-lg bg-accent/10 flex items-center justify-center shrink-0 mt-0.5">
                  <Sparkles size={13} className="text-accent" />
                </div>
                <TypingDots />
              </motion.div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input bar */}
      <div className="shrink-0 px-4 pb-4 pt-2">
        <div className="max-w-2xl mx-auto">
          <div className="relative flex items-end gap-2 border border-border rounded-2xl bg-card/50 px-4 py-3 focus-within:border-accent/30 transition-colors">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything..."
              rows={1}
              disabled={sending}
              className="flex-1 bg-transparent text-[13px] placeholder:text-muted-foreground/40 outline-none resize-none min-h-[20px] max-h-[160px] leading-relaxed"
            />
            <button
              onClick={() => sendMessage()}
              disabled={!input.trim() || sending}
              className={`shrink-0 w-8 h-8 rounded-xl flex items-center justify-center transition-all duration-150 ${
                input.trim() && !sending
                  ? "bg-accent text-accent-foreground hover:opacity-90"
                  : "bg-foreground/[0.05] text-muted-foreground/30"
              }`}
            >
              {sending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <ArrowUp size={14} />
              )}
            </button>
          </div>
          <p className="text-[10px] text-muted-foreground/40 text-center mt-2">
            Panacea can make mistakes. Verify important information.
          </p>
        </div>
      </div>
    </div>
  );
}

function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[70%] px-4 py-2.5 rounded-2xl rounded-br-md bg-accent/[0.12] text-[13px] leading-relaxed">
        {content}
      </div>
    </div>
  );
}

function AssistantBubble({ content }: { content: string }) {
  return (
    <div className="flex items-start gap-3">
      <div className="w-7 h-7 rounded-lg bg-accent/10 flex items-center justify-center shrink-0 mt-0.5">
        <Sparkles size={13} className="text-accent" />
      </div>
      <div className="flex-1 text-[13px] leading-relaxed whitespace-pre-wrap min-w-0">
        {content}
      </div>
    </div>
  );
}

function ToolLoadingIndicator({ toolName }: { toolName: string }) {
  const label = TOOL_LABELS[toolName] || "Working";
  return (
    <div className="flex items-center gap-2.5 text-[12px] text-muted-foreground py-1 pl-10">
      <Loader2 size={12} className="animate-spin text-accent/60" />
      <span>{label}...</span>
    </div>
  );
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1 py-2">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-pulse"
          style={{ animationDelay: `${i * 200}ms` }}
        />
      ))}
    </div>
  );
}
