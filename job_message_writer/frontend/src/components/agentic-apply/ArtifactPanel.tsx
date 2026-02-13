"use client";

import { X } from "lucide-react";
import type { Artifact } from "@/hooks/useArtifactPanel";
import InlineMessagePreview from "./inline-results/InlineMessagePreview";
import InlineResumeViewer from "./inline-results/InlineResumeViewer";
import InlineATSScore from "./inline-results/InlineATSScore";

interface Props {
  artifact: Artifact | null;
  artifacts: Artifact[];
  onClose: () => void;
  onSwitchArtifact: (id: string) => void;
  onSendMessage?: (text: string) => void;
}

export default function ArtifactPanel({
  artifact,
  artifacts,
  onClose,
  onSwitchArtifact,
  onSendMessage,
}: Props) {
  if (!artifact) return null;

  return (
    <div className="flex flex-col h-full border-l border-[#222] bg-black">
      {/* Header */}
      <div className="flex items-center justify-between px-4 h-12 shrink-0 border-b border-[#222]">
        <span className="text-[13px] font-medium text-[#ededed] truncate pr-3">
          {artifact.title}
        </span>
        <button
          onClick={onClose}
          className="w-7 h-7 flex items-center justify-center rounded-md text-[#555] hover:text-[#ededed] hover:bg-[#111] transition-colors shrink-0"
        >
          <X size={14} />
        </button>
      </div>

      {/* Tab bar (when 2+ artifacts) */}
      {artifacts.length > 1 && (
        <div className="flex items-center gap-1 px-4 py-2 border-b border-[#222] overflow-x-auto">
          {artifacts.map((a) => (
            <button
              key={a.id}
              onClick={() => onSwitchArtifact(a.id)}
              className={`px-2.5 py-1 rounded-md text-[11px] whitespace-nowrap transition-colors ${
                a.id === artifact.id
                  ? "bg-[#1a1a1a] text-[#ededed]"
                  : "text-[#666] hover:text-[#888]"
              }`}
            >
              {a.title}
            </button>
          ))}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        <ArtifactContent
          artifact={artifact}
          onSendMessage={onSendMessage}
        />
      </div>
    </div>
  );
}

function ArtifactContent({
  artifact,
  onSendMessage,
}: {
  artifact: Artifact;
  onSendMessage?: (text: string) => void;
}) {
  const data = artifact.data as Record<string, unknown>;

  switch (artifact.type) {
    case "message_preview":
      return (
        <InlineMessagePreview data={data} onSendMessage={onSendMessage} />
      );
    case "resume_tailored":
      return <InlineResumeViewer data={data} />;
    case "resume_score":
      return <InlineATSScore data={data} />;
    default:
      return null;
  }
}
