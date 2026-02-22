"use client";

import { X } from "lucide-react";
import type { Artifact, ArtifactVersion } from "@/hooks/useArtifactPanel";
import InlineMessagePreview from "./inline-results/InlineMessagePreview";
import InlineResumeViewer from "./inline-results/InlineResumeViewer";
import InlineATSScore from "./inline-results/InlineATSScore";

interface Props {
  artifact: Artifact | null;
  artifacts: Artifact[];
  onClose: () => void;
  onSwitchArtifact: (id: string) => void;
  onSendMessage?: (text: string) => void;
  onSetVersion?: (artifactId: string, versionIdx: number) => void;
}

export default function ArtifactPanel({
  artifact,
  artifacts,
  onClose,
  onSwitchArtifact,
  onSendMessage,
  onSetVersion,
}: Props) {
  if (!artifact) return null;

  const versions = artifact.versions;
  const activeVersionIdx = artifact.activeVersionIdx ?? 0;

  return (
    <div className="flex flex-col h-full border-l border-[#222] bg-black">
      {/* Header */}
      <div className="flex items-center justify-between px-4 h-12 shrink-0 border-b border-[#222]">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[13px] font-medium text-[#ededed] truncate pr-3">
            {artifact.title}
          </span>
          {/* Version dropdown — always visible for resume artifacts */}
          {versions && versions.length >= 1 && onSetVersion && (
            <select
              value={activeVersionIdx}
              onChange={(e) => onSetVersion(artifact.id, Number(e.target.value))}
              className="bg-[#111] border border-[#333] rounded-md px-2 py-0.5 text-[11px] text-[#ededed] outline-none cursor-pointer hover:border-[#555] transition-colors shrink-0"
            >
              {versions.map((v, i) => (
                <option key={v.messageId} value={i}>
                  v{i + 1}
                </option>
              ))}
            </select>
          )}
        </div>
        <button
          onClick={onClose}
          className="w-7 h-7 flex items-center justify-center rounded-md text-[#555] hover:text-[#ededed] hover:bg-[#111] transition-colors shrink-0"
        >
          <X size={14} />
        </button>
      </div>

      {/* Content — resume gets full height with no padding */}
      <div
        className={`flex-1 min-h-0 ${
          artifact.type === "resume_tailored"
            ? ""
            : "overflow-y-auto p-4"
        }`}
      >
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
