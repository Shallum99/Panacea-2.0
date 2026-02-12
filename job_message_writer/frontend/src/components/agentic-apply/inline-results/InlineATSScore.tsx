"use client";

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

  return (
    <div className="rounded-lg border border-[#222] bg-[#0a0a0a] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1a1a1a]">
        <span className="text-[12px] font-medium text-[#ededed]">
          ATS Score{data.resume_title ? ` \u2014 ${data.resume_title}` : ""}
        </span>
        <span className="text-sm font-bold text-[#ededed] tabular-nums">
          {score}
        </span>
      </div>

      {/* Bar */}
      <div className="px-4 py-3 border-b border-[#1a1a1a]">
        <div className="h-1.5 rounded-full bg-[#1a1a1a] overflow-hidden">
          <div
            className="h-full rounded-full bg-[#ededed] transition-all duration-700"
            style={{ width: `${Math.min(score, 100)}%` }}
          />
        </div>
      </div>

      <div className="px-4 py-3 space-y-3">
        {/* Strengths */}
        {data.strengths && data.strengths.length > 0 && (
          <div>
            <p className="text-[11px] font-medium text-[#ededed] mb-1">
              Strengths
            </p>
            {data.strengths.map((s, i) => (
              <p
                key={i}
                className="text-[12px] text-[#888] leading-relaxed"
              >
                + {s}
              </p>
            ))}
          </div>
        )}

        {/* Improvements */}
        {data.improvements && data.improvements.length > 0 && (
          <div>
            <p className="text-[11px] font-medium text-[#ededed] mb-1">
              Areas to Improve
            </p>
            {data.improvements.map((s, i) => (
              <p
                key={i}
                className="text-[12px] text-[#888] leading-relaxed"
              >
                - {s}
              </p>
            ))}
          </div>
        )}

        {/* Missing keywords */}
        {data.missing_keywords && data.missing_keywords.length > 0 && (
          <div>
            <p className="text-[11px] font-medium text-[#ededed] mb-1.5">
              Missing Keywords
            </p>
            <div className="flex flex-wrap gap-1">
              {data.missing_keywords.map((kw, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 rounded bg-[#1a1a1a] text-[#888] text-[10px]"
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
