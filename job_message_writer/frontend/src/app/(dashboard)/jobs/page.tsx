"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import api from "@/lib/api";

interface JobDescription {
  id: number;
  title: string;
  company_name: string | null;
  content: string;
  url: string | null;
  created_at: string | null;
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<JobDescription[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const { data } = await api.get("/job-descriptions/");
        setJobs(data);
      } catch {
        // silently fail
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Jobs</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Saved job descriptions from your applications
          </p>
        </div>
        <Link
          href="/generate"
          className="px-4 py-2 bg-accent text-accent-foreground text-sm font-medium rounded-lg hover:opacity-90 transition-opacity"
        >
          New Application
        </Link>
      </div>

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-16 bg-muted/30 animate-pulse rounded-lg"
            />
          ))}
        </div>
      ) : jobs.length === 0 ? (
        <div className="border border-border rounded-lg p-8 text-center">
          <p className="text-sm text-muted-foreground">
            No jobs saved yet. Jobs are created automatically when you generate
            a message.
          </p>
        </div>
      ) : (
        <div className="border border-border rounded-lg divide-y divide-border">
          {jobs.map((job) => (
            <div
              key={job.id}
              className="px-4 py-3 hover:bg-muted/30 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">
                    {job.title || "Untitled"}
                    {job.company_name && (
                      <span className="text-muted-foreground font-normal">
                        {" "}
                        at {job.company_name}
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                    {job.content?.slice(0, 120)}...
                  </p>
                </div>
                <div className="flex items-center gap-2 ml-4 shrink-0">
                  {job.url && (
                    <a
                      href={job.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-accent hover:underline"
                    >
                      View
                    </a>
                  )}
                  <Link
                    href={`/generate?job=${job.id}`}
                    className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    Apply
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
