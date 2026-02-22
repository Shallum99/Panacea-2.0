"use client";

import { Loader2, Download, Trash2, Eye } from "lucide-react";

interface Props {
  draftCount: number;
  isGenerating: boolean;
  hasGenerated: boolean;
  onGenerate: () => void;
  onClearAll: () => void;
  onViewChanges?: () => void;
}

export default function DraftBanner({
  draftCount,
  isGenerating,
  hasGenerated,
  onGenerate,
  onClearAll,
  onViewChanges,
}: Props) {
  if (draftCount === 0 && !hasGenerated) return null;

  return (
    <div className="flex items-center justify-between px-4 py-2.5 border-t border-border bg-muted/30">
      <div className="flex items-center gap-3">
        {draftCount > 0 && (
          <span className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{draftCount}</span>{" "}
            pending {draftCount === 1 ? "change" : "changes"}
          </span>
        )}
        {hasGenerated && draftCount === 0 && (
          <span className="text-xs text-accent">Resume generated</span>
        )}
      </div>

      <div className="flex items-center gap-2">
        {onViewChanges && draftCount > 0 && (
          <button
            onClick={onViewChanges}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors rounded-md hover:bg-muted"
          >
            <Eye className="w-3.5 h-3.5" />
            View
          </button>
        )}
        {draftCount > 0 && (
          <button
            onClick={onClearAll}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-muted-foreground hover:text-red-400 transition-colors rounded-md hover:bg-muted"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Clear
          </button>
        )}
        {draftCount > 0 && (
          <button
            onClick={onGenerate}
            disabled={isGenerating}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-accent text-accent-foreground rounded-md hover:bg-accent/90 transition-colors disabled:opacity-50"
          >
            {isGenerating ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Download className="w-3.5 h-3.5" />
                Generate Resume
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}
