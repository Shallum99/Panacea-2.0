"use client";

import { useState } from "react";
import { ExternalLink, ChevronDown, ChevronUp, Briefcase } from "lucide-react";

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
    <div className="border-l-2 border-accent/40 rounded-xl bg-card/60 overflow-hidden ml-10">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border/50">
        <div className="flex items-center gap-2">
          <Briefcase size={13} className="text-accent" />
          <span className="text-[13px] font-medium">{data.title}</span>
        </div>
        <p className="text-[11px] text-muted-foreground mt-0.5 pl-5">
          {data.company}
          {data.location ? ` \u2014 ${data.location}` : ""}
        </p>
      </div>

      {/* Content */}
      {data.content && (
        <div className="px-4 py-3">
          <div
            className={`text-[12px] text-muted-foreground leading-relaxed whitespace-pre-wrap ${
              !expanded ? "max-h-[120px] overflow-hidden" : ""
            }`}
          >
            {data.content}
          </div>
          {(data.content.length > 400 ||
            (data.full_content_length && data.full_content_length > 400)) && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-[11px] text-accent mt-2 hover:underline"
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
        <div className="px-4 py-2.5 border-t border-border/50">
          <a
            href={data.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-[11px] text-accent hover:underline"
          >
            <ExternalLink size={10} /> View original listing
          </a>
        </div>
      )}
    </div>
  );
}
