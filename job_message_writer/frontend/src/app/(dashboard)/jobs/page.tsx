"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import api from "@/lib/api";
import {
  searchJobs,
  getJobDetail,
  createJdFromUrl,
  getSavedJobs,
  type JobSearchResult,
  type SavedJob,
} from "@/lib/api/jobSearch";

const SOURCE_BADGE: Record<string, string> = {
  greenhouse: "GH",
  lever: "LV",
  url: "URL",
  manual: "",
};

export default function JobsPage() {
  const router = useRouter();

  // URL import
  const [urlInput, setUrlInput] = useState("");
  const [fetchingUrl, setFetchingUrl] = useState(false);

  // Search
  const [searchCompany, setSearchCompany] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchLocation, setSearchLocation] = useState("");
  const [searchSource, setSearchSource] = useState("");
  const [searchResults, setSearchResults] = useState<JobSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  // Saved jobs
  const [savedJobs, setSavedJobs] = useState<SavedJob[]>([]);
  const [loadingSaved, setLoadingSaved] = useState(true);

  // Apply loading
  const [savingJobId, setSavingJobId] = useState<string | null>(null);

  useEffect(() => {
    getSavedJobs()
      .then(setSavedJobs)
      .catch(() => {})
      .finally(() => setLoadingSaved(false));
  }, []);

  async function handleFetchUrl() {
    if (!urlInput.trim()) return;
    setFetchingUrl(true);
    try {
      const saved = await createJdFromUrl(urlInput.trim());
      toast.success("Job imported successfully");
      setSavedJobs((prev) => [saved, ...prev]);
      setUrlInput("");
      router.push(`/generate?job=${saved.id}`);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Failed to fetch job listing";
      toast.error(detail);
    } finally {
      setFetchingUrl(false);
    }
  }

  async function handleSearch() {
    if (!searchCompany && !searchQuery) {
      toast.error("Enter a company or keyword to search");
      return;
    }
    setSearching(true);
    setHasSearched(true);
    try {
      const res = await searchJobs({
        q: searchQuery || undefined,
        company: searchCompany || undefined,
        location: searchLocation || undefined,
        source: searchSource || undefined,
      });
      setSearchResults(res.results);
      if (res.results.length === 0) {
        toast("No jobs found. Try a different company or keyword.");
      }
    } catch {
      toast.error("Search failed");
    } finally {
      setSearching(false);
    }
  }

  async function handleApplyFromSearch(job: JobSearchResult) {
    setSavingJobId(job.id);
    try {
      // Get full JD content
      const detail = await getJobDetail(job.source, job.company, job.id);
      // Save to user's JDs
      const { data: saved } = await api.post("/job-descriptions/", {
        title: detail.title,
        content: detail.content,
        url: detail.url,
        source: detail.source,
      });
      router.push(`/generate?job=${saved.id}`);
    } catch {
      toast.error("Failed to load job details");
    } finally {
      setSavingJobId(null);
    }
  }

  return (
    <div className="space-y-8 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Jobs</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Import from a URL or search public job boards
          </p>
        </div>
        <Link
          href="/generate"
          className="px-4 py-2 bg-accent text-accent-foreground text-sm font-medium rounded-lg hover:opacity-90 transition-opacity"
        >
          New Application
        </Link>
      </div>

      {/* 1. Import from URL */}
      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Import from URL
        </h2>
        <div className="border border-border rounded-lg p-4">
          <div className="flex gap-2">
            <input
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleFetchUrl()}
              placeholder="Paste a job listing URL (Greenhouse, Lever, or any site)"
              className="flex-1 px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-accent"
            />
            <button
              onClick={handleFetchUrl}
              disabled={fetchingUrl || !urlInput.trim()}
              className="px-4 py-2 text-sm font-medium bg-accent text-accent-foreground rounded-lg hover:opacity-90 disabled:opacity-40 whitespace-nowrap"
            >
              {fetchingUrl ? "Fetching..." : "Fetch & Apply"}
            </button>
          </div>
          <p className="text-[10px] text-muted-foreground mt-2">
            Works with Greenhouse, Lever, and most job listing pages. Auto-extracts the job description.
          </p>
        </div>
      </section>

      {/* 2. Search Job Boards */}
      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Search Job Boards
        </h2>
        <div className="border border-border rounded-lg p-4 space-y-3">
          <div className="grid grid-cols-4 gap-2">
            <input
              value={searchCompany}
              onChange={(e) => setSearchCompany(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="Company (e.g. stripe)"
              className="px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-accent"
            />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="Keyword (e.g. engineer)"
              className="px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-accent"
            />
            <input
              value={searchLocation}
              onChange={(e) => setSearchLocation(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="Location (e.g. remote)"
              className="px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-accent"
            />
            <div className="flex gap-2">
              <select
                value={searchSource}
                onChange={(e) => setSearchSource(e.target.value)}
                className="flex-1 px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-accent"
              >
                <option value="">All</option>
                <option value="greenhouse">Greenhouse</option>
                <option value="lever">Lever</option>
              </select>
              <button
                onClick={handleSearch}
                disabled={searching}
                className="px-4 py-2 text-sm font-medium bg-accent text-accent-foreground rounded-lg hover:opacity-90 disabled:opacity-40 whitespace-nowrap"
              >
                {searching ? "..." : "Search"}
              </button>
            </div>
          </div>

          {/* Search results */}
          {searching && (
            <div className="grid grid-cols-2 gap-2">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-24 bg-muted/30 animate-pulse rounded-lg" />
              ))}
            </div>
          )}

          {!searching && hasSearched && searchResults.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-4">
              No results found
            </p>
          )}

          {!searching && searchResults.length > 0 && (
            <div className="grid grid-cols-2 gap-2 max-h-[400px] overflow-y-auto">
              {searchResults.map((job) => (
                <div
                  key={`${job.source}-${job.id}`}
                  className="border border-border rounded-lg p-3 hover:border-muted-foreground/30 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">{job.title}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {job.company}
                        {job.location && ` \u2022 ${job.location}`}
                      </p>
                      {job.department && (
                        <p className="text-[10px] text-muted-foreground/60 mt-0.5 truncate">
                          {job.department}
                        </p>
                      )}
                    </div>
                    <span className="text-[9px] px-1.5 py-0.5 bg-muted rounded text-muted-foreground shrink-0 uppercase font-mono">
                      {SOURCE_BADGE[job.source] || job.source}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <a
                      href={job.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-accent hover:underline"
                    >
                      View
                    </a>
                    <button
                      onClick={() => handleApplyFromSearch(job)}
                      disabled={savingJobId === job.id}
                      className="text-xs text-foreground hover:text-accent disabled:opacity-40"
                    >
                      {savingJobId === job.id ? "Loading..." : "Apply"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* 3. Saved Jobs */}
      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Saved Jobs ({savedJobs.length})
        </h2>
        <div className="border border-border rounded-lg divide-y divide-border">
          {loadingSaved ? (
            <div className="space-y-0">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-14 bg-muted/20 animate-pulse" />
              ))}
            </div>
          ) : savedJobs.length === 0 ? (
            <div className="px-4 py-8 text-center">
              <p className="text-sm text-muted-foreground">
                No saved jobs yet. Import from a URL or search above, or jobs are saved automatically when you generate a message.
              </p>
            </div>
          ) : (
            savedJobs.map((job) => {
              const companyName =
                job.company_info &&
                typeof job.company_info === "object" &&
                "company_name" in job.company_info
                  ? (job.company_info.company_name as string)
                  : null;
              return (
                <div
                  key={job.id}
                  className="px-4 py-3 hover:bg-muted/30 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <div className="min-w-0 flex-1 flex items-center gap-2">
                      <p className="text-sm font-medium truncate">
                        {job.title || "Untitled"}
                        {companyName &&
                          companyName !== "Unknown" && (
                            <span className="text-muted-foreground font-normal">
                              {" "}at {companyName}
                            </span>
                          )}
                      </p>
                      {job.source && SOURCE_BADGE[job.source] && (
                        <span className="text-[9px] px-1.5 py-0.5 bg-muted rounded text-muted-foreground shrink-0 uppercase font-mono">
                          {SOURCE_BADGE[job.source]}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 ml-4 shrink-0">
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
              );
            })
          )}
        </div>
      </section>
    </div>
  );
}
