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
      className={`relative w-9 h-9 flex items-center justify-center rounded-full border transition-all duration-200 ${
        active
          ? "border-accent/30 text-accent hover:bg-accent/10"
          : "border-border text-muted-foreground hover:text-foreground hover:border-foreground/20"
      }`}
    >
      <SlidersHorizontal size={15} />
      {active && (
        <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-success border-2 border-card" />
      )}
    </button>
  );
}
