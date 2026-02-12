"use client";

import { Star } from "lucide-react";

interface ScoreData {
  score?: number;
  strengths?: string[];
  improvements?: string[];
  missing_keywords?: string[];
  resume_title?: string;
}

interface Props {
  data: ScoreData;
}

export default function InlineATSScore({ data }: Props) {
  const score = data.score || 0;
  const color =
    score >= 75
      ? "text-success"
      : score >= 50
        ? "text-accent"
        : "text-destructive";
  const bgColor =
    score >= 75
      ? "bg-success/10"
      : score >= 50
        ? "bg-accent/10"
        : "bg-destructive/10";

  return (
    <div className="border-l-2 border-accent/40 rounded-xl bg-card/60 overflow-hidden ml-10">
      {/* Header with score */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
        <div className="flex items-center gap-2">
          <Star size={13} className="text-accent" />
          <span className="text-[12px] font-medium">
            ATS Score {data.resume_title && `\u2014 ${data.resume_title}`}
          </span>
        </div>
        <div
          className={`px-3 py-1 rounded-full ${bgColor} ${color} text-sm font-bold`}
        >
          {score}
        </div>
      </div>

      {/* Score bar */}
      <div className="px-4 py-3 border-b border-border/50">
        <div className="h-2 rounded-full bg-foreground/[0.05] overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ${
              score >= 75
                ? "bg-success"
                : score >= 50
                  ? "bg-accent"
                  : "bg-destructive"
            }`}
            style={{ width: `${Math.min(score, 100)}%` }}
          />
        </div>
      </div>

      <div className="px-4 py-3 space-y-3">
        {/* Strengths */}
        {data.strengths && data.strengths.length > 0 && (
          <div>
            <p className="text-[11px] font-medium text-success mb-1">
              Strengths
            </p>
            {data.strengths.map((s, i) => (
              <p
                key={i}
                className="text-[12px] text-muted-foreground leading-relaxed"
              >
                + {s}
              </p>
            ))}
          </div>
        )}

        {/* Improvements */}
        {data.improvements && data.improvements.length > 0 && (
          <div>
            <p className="text-[11px] font-medium text-destructive mb-1">
              Areas to Improve
            </p>
            {data.improvements.map((s, i) => (
              <p
                key={i}
                className="text-[12px] text-muted-foreground leading-relaxed"
              >
                - {s}
              </p>
            ))}
          </div>
        )}

        {/* Missing keywords */}
        {data.missing_keywords && data.missing_keywords.length > 0 && (
          <div>
            <p className="text-[11px] font-medium text-muted-foreground mb-1.5">
              Missing Keywords
            </p>
            <div className="flex flex-wrap gap-1">
              {data.missing_keywords.map((kw, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 rounded-full bg-destructive/10 text-destructive text-[10px]"
                >
                  {kw}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
