"use client";

import { useRef, useEffect } from "react";
import { ArrowUp, Loader2 } from "lucide-react";
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
  "Generate a cover letter for this role",
  "Tailor my resume to match this JD",
  "Check my ATS compatibility score",
  "Search for similar open positions",
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
    <div className="flex flex-col flex-1 min-h-0">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto" onScroll={onScroll}>
        {showWelcome ? (
          <div className="flex flex-col items-center justify-center h-full px-4">
            <div className="max-w-lg w-full text-center">
              <h1 className="text-2xl font-semibold text-[#ededed] mb-2">
                What do you want to apply for?
              </h1>
              <p className="text-[13px] text-[#666] mb-8">
                {contextReady
                  ? "Your context is set. Choose an action or type a message."
                  : "Set your application context to get started."}
              </p>
              {contextReady ? (
                <div className="grid grid-cols-2 gap-2 max-w-md mx-auto">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => sendMessage(s)}
                      className="px-3 py-2.5 rounded-lg text-[12px] text-left text-[#888] border border-[#222] hover:border-[#444] hover:text-[#ededed] bg-transparent transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              ) : (
                <button
                  onClick={onOpenContext}
                  className="px-4 py-2 text-[13px] font-medium text-black bg-[#ededed] rounded-lg hover:bg-white transition-colors"
                >
                  Set Context
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="max-w-2xl mx-auto px-4 py-6 space-y-5">
            {messages.map((msg) => (
              <div key={msg.id}>
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
              </div>
            ))}
            {sending && messages[messages.length - 1]?.role !== "tool" && (
              <div className="flex items-center gap-2 py-1">
                <TypingDots />
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="shrink-0 px-4 pb-4 pt-2">
        <div className="max-w-2xl mx-auto">
          <div className="relative flex items-end gap-2 border border-[#333] rounded-xl bg-[#0a0a0a] px-4 py-3 focus-within:border-[#555] transition-colors">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Send a message..."
              rows={1}
              disabled={sending}
              className="flex-1 bg-transparent text-[13px] text-[#ededed] placeholder:text-[#555] outline-none resize-none min-h-[20px] max-h-[160px] leading-relaxed"
            />
            <button
              onClick={() => sendMessage()}
              disabled={!input.trim() || sending}
              className={`shrink-0 w-7 h-7 rounded-lg flex items-center justify-center transition-all ${
                input.trim() && !sending
                  ? "bg-[#ededed] text-black hover:bg-white"
                  : "bg-[#222] text-[#555]"
              }`}
            >
              {sending ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <ArrowUp size={13} />
              )}
            </button>
          </div>
          <p className="text-[10px] text-[#444] text-center mt-2">
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
      <div className="max-w-[75%] px-4 py-2.5 rounded-2xl rounded-br-sm bg-[#1a1a1a] text-[13px] text-[#ededed] leading-relaxed">
        {content}
      </div>
    </div>
  );
}

function AssistantBubble({ content }: { content: string }) {
  return (
    <div className="text-[13px] text-[#ededed] leading-relaxed whitespace-pre-wrap">
      {content}
    </div>
  );
}

function ToolLoadingIndicator({ toolName }: { toolName: string }) {
  const label = TOOL_LABELS[toolName] || "Working";
  return (
    <div className="flex items-center gap-2 text-[12px] text-[#666] py-1">
      <Loader2 size={12} className="animate-spin" />
      <span>{label}...</span>
    </div>
  );
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1 py-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-[#444] animate-pulse"
          style={{ animationDelay: `${i * 200}ms` }}
        />
      ))}
    </div>
  );
}
