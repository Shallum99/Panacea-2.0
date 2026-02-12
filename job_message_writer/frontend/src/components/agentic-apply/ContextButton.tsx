"use client";

import { SlidersHorizontal, ArrowLeft } from "lucide-react";
import type { ChatContext } from "@/lib/api/chat";

interface Props {
  context: ChatContext;
  onClick: () => void;
  showHint?: boolean;
}

function hasContext(ctx: ChatContext): boolean {
  return !!(ctx.job_description || ctx.resume_id || ctx.position_title);
}

export default function ContextButton({ context, onClick, showHint }: Props) {
  const active = hasContext(context);
  const empty = !active;

  return (
    <div className="flex items-center gap-2">
      {/* Arrow hint when context is empty */}
      {showHint && empty && (
        <div className="flex items-center gap-1.5 animate-pulse">
          <span className="text-[12px] text-[#888]">
            Set your context
          </span>
          <ArrowLeft size={13} className="text-[#888] rotate-180" />
        </div>
      )}

      <button
        onClick={onClick}
        title="Application Context"
        className={`relative w-8 h-8 flex items-center justify-center rounded-lg border transition-colors ${
          active
            ? "border-[#333] text-[#ededed] hover:bg-[#111]"
            : "border-[#222] text-[#666] hover:text-[#ededed] hover:border-[#444]"
        }`}
      >
        <SlidersHorizontal size={14} />
        {active && (
          <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-[#50e3c2] border-2 border-black" />
        )}
        {/* Pulsing ring when empty */}
        {empty && showHint && (
          <span className="absolute inset-0 rounded-lg border border-[#444] animate-ping opacity-30" />
        )}
      </button>
    </div>
  );
}
