"use client";

import { SlidersHorizontal } from "lucide-react";
import type { ChatContext } from "@/lib/api/chat";

interface Props {
  context: ChatContext;
  onClick: () => void;
}

function hasContext(ctx: ChatContext): boolean {
  return !!(ctx.job_description || ctx.resume_id || ctx.position_title);
}

export default function ContextButton({ context, onClick }: Props) {
  const active = hasContext(context);

  return (
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
    </button>
  );
}
