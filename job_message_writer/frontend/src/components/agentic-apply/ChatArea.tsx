"use client";

import { useRef, useEffect } from "react";
import { ArrowUp, ArrowUpRight, Loader2, FileText, Briefcase, SlidersHorizontal } from "lucide-react";
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
  onOpenArtifact?: (messageId: string) => void;
  activeArtifactMessageId?: string | null;
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
  onOpenArtifact,
  activeArtifactMessageId,
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
          contextReady ? (
            /* ── Context is set: show suggestions ── */
            <div className="flex flex-col items-center justify-center h-full px-4">
              <div className="max-w-lg w-full text-center">
                <h1 className="text-2xl font-semibold text-[#ededed] mb-2">
                  Ready to go
                </h1>
                <p className="text-[13px] text-[#666] mb-1">
                  {context.position_title && (
                    <span className="text-[#999]">{context.position_title}</span>
                  )}
                  {context.position_title && context.job_description && (
                    <span className="text-[#444]"> &middot; </span>
                  )}
                  {context.job_description && (
                    <span className="text-[#666]">JD loaded</span>
                  )}
                  {context.resume_id && (
                    <>
                      <span className="text-[#444]"> &middot; </span>
                      <span className="text-[#666]">Resume selected</span>
                    </>
                  )}
                </p>
                <p className="text-[13px] text-[#555] mb-8">
                  Choose an action or type a message below.
                </p>
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
              </div>
            </div>
          ) : (
            /* ── No context: big prominent CTA ── */
            <div className="flex flex-col items-center justify-center h-full px-4">
              <div className="max-w-md w-full">
                {/* Big arrow pointing to top-right context button */}
                <div className="flex justify-end mb-6 pr-2">
                  <div className="flex items-center gap-2 animate-bounce">
                    <span className="text-[13px] text-[#888] font-medium">
                      Click here to start
                    </span>
                    <ArrowUpRight size={20} className="text-[#ededed]" />
                  </div>
                </div>

                {/* Main card */}
                <button
                  onClick={onOpenContext}
                  className="w-full text-left p-6 rounded-xl border border-[#222] bg-[#0a0a0a] hover:border-[#444] transition-all group cursor-pointer"
                >
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 rounded-lg bg-[#111] border border-[#222] flex items-center justify-center group-hover:border-[#444] transition-colors">
                      <SlidersHorizontal size={18} className="text-[#ededed]" />
                    </div>
                    <div>
                      <h2 className="text-[16px] font-semibold text-[#ededed]">
                        Set Application Context
                      </h2>
                      <p className="text-[12px] text-[#666]">
                        Required before you can chat
                      </p>
                    </div>
                  </div>

                  <div className="space-y-3 ml-[52px]">
                    <div className="flex items-start gap-3">
                      <div className="w-5 h-5 rounded-full border border-[#333] flex items-center justify-center shrink-0 mt-0.5">
                        <span className="text-[10px] text-[#666] font-bold">1</span>
                      </div>
                      <div>
                        <p className="text-[13px] text-[#ededed]">Paste the job description</p>
                        <p className="text-[11px] text-[#555]">Or paste a URL / upload a PDF</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3">
                      <div className="w-5 h-5 rounded-full border border-[#333] flex items-center justify-center shrink-0 mt-0.5">
                        <span className="text-[10px] text-[#666] font-bold">2</span>
                      </div>
                      <div>
                        <p className="text-[13px] text-[#ededed]">Select your resume</p>
                        <p className="text-[11px] text-[#555]">We&apos;ll tailor it to the JD</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3">
                      <div className="w-5 h-5 rounded-full border border-[#333] flex items-center justify-center shrink-0 mt-0.5">
                        <span className="text-[10px] text-[#666] font-bold">3</span>
                      </div>
                      <div>
                        <p className="text-[13px] text-[#ededed]">Choose message type</p>
                        <p className="text-[11px] text-[#555]">Email, LinkedIn, cover letter, etc.</p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-5 ml-[52px]">
                    <span className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#ededed] text-black text-[13px] font-medium group-hover:bg-white transition-colors">
                      <SlidersHorizontal size={14} />
                      Open Context
                    </span>
                  </div>
                </button>

                {/* Secondary hints */}
                <div className="flex items-center justify-center gap-6 mt-6">
                  <div className="flex items-center gap-2 text-[11px] text-[#555]">
                    <FileText size={12} />
                    <span>Supports PDF upload</span>
                  </div>
                  <div className="flex items-center gap-2 text-[11px] text-[#555]">
                    <Briefcase size={12} />
                    <span>Auto-extracts fields</span>
                  </div>
                </div>
              </div>
            </div>
          )
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
                      onOpenArtifact={onOpenArtifact}
                      activeArtifactMessageId={activeArtifactMessageId}
                      messageId={msg.id}
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
