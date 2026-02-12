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
      <div className="ml-10 text-[12px] text-muted-foreground/50 py-2">
        No jobs found matching your search.
      </div>
    );
  }

  return (
    <div className="ml-10 space-y-1.5">
      {jobs.slice(0, 10).map((job, i) => (
        <div
          key={i}
          className="flex items-center justify-between px-4 py-2.5 rounded-xl border border-border bg-card/40 hover:border-accent/20 transition-colors"
        >
          <div className="min-w-0 flex-1">
            <p className="text-[12px] font-medium truncate">{job.title}</p>
            <div className="flex items-center gap-3 text-[11px] text-muted-foreground mt-0.5">
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
            <span className="px-2 py-0.5 rounded-full bg-foreground/[0.05] text-[10px] text-muted-foreground">
              {job.source}
            </span>
            {job.url && (
              <a
                href={job.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-muted-foreground hover:text-foreground transition-colors"
              >
                <ExternalLink size={12} />
              </a>
            )}
          </div>
        </div>
      ))}
      {(data.total || 0) > 10 && (
        <p className="text-[10px] text-muted-foreground/50 text-center pt-1">
          +{(data.total || 0) - 10} more results
        </p>
      )}
    </div>
  );
}
