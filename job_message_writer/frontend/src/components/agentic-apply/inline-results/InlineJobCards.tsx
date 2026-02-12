"use client";

import { Briefcase, MapPin, ExternalLink } from "lucide-react";

interface JobItem {
  title?: string;
  company?: string;
  location?: string;
  source?: string;
  url?: string;
  department?: string;
}

interface JobCardsData {
  jobs?: JobItem[];
  total?: number;
}

interface Props {
  data: JobCardsData;
  onUseJD?: (job: JobItem) => void;
}

export default function InlineJobCards({ data, onUseJD }: Props) {
  const jobs = data.jobs || [];

  if (jobs.length === 0) {
    return (
      <div className="text-[12px] text-[#555] py-2">
        No jobs found matching your search.
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {jobs.slice(0, 10).map((job, i) => (
        <div
          key={i}
          className="flex items-center justify-between px-4 py-2.5 rounded-lg border border-[#222] bg-[#0a0a0a] hover:border-[#333] transition-colors"
        >
          <div className="min-w-0 flex-1">
            <p className="text-[12px] font-medium text-[#ededed] truncate">
              {job.title}
            </p>
            <div className="flex items-center gap-3 text-[11px] text-[#666] mt-0.5">
              <span className="flex items-center gap-1">
                <Briefcase size={10} />
                {job.company}
              </span>
              {job.location && (
                <span className="flex items-center gap-1">
                  <MapPin size={10} />
                  {job.location}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0 ml-3">
            <span className="px-2 py-0.5 rounded bg-[#1a1a1a] text-[10px] text-[#666]">
              {job.source}
            </span>
            {job.url && (
              <a
                href={job.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#555] hover:text-[#ededed] transition-colors"
              >
                <ExternalLink size={12} />
              </a>
            )}
          </div>
        </div>
      ))}
      {(data.total || 0) > 10 && (
        <p className="text-[10px] text-[#555] text-center pt-1">
          +{(data.total || 0) - 10} more results
        </p>
      )}
    </div>
  );
}
