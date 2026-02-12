"use client";

import { useState } from "react";
import { ExternalLink, ChevronDown, ChevronUp } from "lucide-react";

interface JobDetailData {
  title?: string;
  company?: string;
  location?: string;
  content?: string;
  url?: string;
  full_content_length?: number;
}

interface Props {
  data: JobDetailData;
}

export default function InlineJobDetail({ data }: Props) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border border-[#222] bg-[#0a0a0a] overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#1a1a1a]">
        <span className="text-[13px] font-medium text-[#ededed]">
          {data.title}
        </span>
        <p className="text-[11px] text-[#666] mt-0.5">
          {data.company}
          {data.location ? ` \u2014 ${data.location}` : ""}
        </p>
      </div>

      {/* Content */}
      {data.content && (
        <div className="px-4 py-3">
          <div
            className={`text-[12px] text-[#888] leading-relaxed whitespace-pre-wrap ${
              !expanded ? "max-h-[120px] overflow-hidden" : ""
            }`}
          >
            {data.content}
          </div>
          {(data.content.length > 400 ||
            (data.full_content_length && data.full_content_length > 400)) && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-[11px] text-[#888] mt-2 hover:text-[#ededed] transition-colors"
            >
              {expanded ? (
                <>
                  <ChevronUp size={12} /> Show less
                </>
              ) : (
                <>
                  <ChevronDown size={12} /> Show more
                </>
              )}
            </button>
          )}
        </div>
      )}

      {/* Footer */}
      {data.url && (
        <div className="px-4 py-2.5 border-t border-[#1a1a1a]">
          <a
            href={data.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-[11px] text-[#888] hover:text-[#ededed] transition-colors"
          >
            <ExternalLink size={10} /> View original listing
          </a>
        </div>
      )}
    </div>
  );
}
