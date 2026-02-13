"use client";

import { FileText, Target, ChevronRight } from "lucide-react";

interface Props {
  type: "message_preview" | "resume_tailored" | "resume_score";
  title: string;
  subtitle?: string;
  isActive: boolean;
  onClick: () => void;
}

const TYPE_CONFIG: Record<
  Props["type"],
  { icon: typeof FileText; label: string }
> = {
  message_preview: { icon: FileText, label: "Message" },
  resume_tailored: { icon: FileText, label: "Resume" },
  resume_score: { icon: Target, label: "ATS Score" },
};

export default function ArtifactCard({
  type,
  title,
  subtitle,
  isActive,
  onClick,
}: Props) {
  const config = TYPE_CONFIG[type];
  const Icon = config.icon;

  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg border transition-colors cursor-pointer text-left ${
        isActive
          ? "border-[#444] bg-[#111]"
          : "border-[#222] bg-[#0a0a0a] hover:border-[#444]"
      }`}
    >
      <div
        className={`w-8 h-8 rounded-md flex items-center justify-center shrink-0 ${
          isActive
            ? "bg-[#1a1a1a] border border-[#333]"
            : "bg-[#1a1a1a] border border-[#222]"
        }`}
      >
        <Icon size={14} className="text-[#888]" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[12px] font-medium text-[#ededed] truncate">
          {title}
        </p>
        {subtitle && (
          <p className="text-[10px] text-[#666] truncate">{subtitle}</p>
        )}
      </div>
      <ChevronRight size={14} className="shrink-0 text-[#555]" />
    </button>
  );
}
