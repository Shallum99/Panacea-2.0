"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { FileText } from "lucide-react";
import { getResumes, setActiveResume, deleteResume, type Resume } from "@/lib/api/resumes";

export default function ResumesPage() {
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<Resume | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    loadResumes();
  }, []);

  async function loadResumes() {
    try {
      const data = await getResumes();
      setResumes(data);
    } catch {
      toast.error("Failed to load resumes");
    } finally {
      setLoading(false);
    }
  }

  async function handleSetActive(id: number) {
    try {
      await setActiveResume(id);
      setResumes((prev) =>
        prev.map((r) => ({ ...r, is_active: r.id === id }))
      );
      toast.success("Active resume updated");
    } catch {
      toast.error("Failed to set active resume");
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteResume(deleteTarget.id);
      setResumes((prev) => prev.filter((r) => r.id !== deleteTarget.id));
      toast.success("Resume deleted");
      setDeleteTarget(null);
    } catch {
      toast.error("Failed to delete resume");
    } finally {
      setDeleting(false);
    }
  }

  // Close modal on Escape
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === "Escape") setDeleteTarget(null);
  }, []);

  useEffect(() => {
    if (deleteTarget) {
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }
  }, [deleteTarget, handleKeyDown]);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Resumes</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {resumes.length} resume{resumes.length !== 1 ? "s" : ""} uploaded
          </p>
        </div>
        <Link
          href="/resumes/upload"
          className="px-4 py-2 bg-accent text-accent-foreground text-sm font-medium rounded-lg hover:opacity-90 transition-opacity"
        >
          Upload Resume
        </Link>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div
              key={i}
              className="border border-border rounded-lg p-5 animate-pulse"
            >
              <div className="h-4 bg-muted rounded w-1/3 mb-3" />
              <div className="h-3 bg-muted rounded w-2/3" />
            </div>
          ))}
        </div>
      ) : resumes.length === 0 ? (
        <div className="card-elevated p-16 text-center">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-muted/50 mb-5">
            <FileText className="w-7 h-7 text-muted-foreground" />
          </div>
          <p className="text-lg font-semibold text-foreground">
            No resumes uploaded yet
          </p>
          <p className="text-sm text-muted-foreground mt-2 max-w-sm mx-auto">
            Upload your resume to unlock tailored cover letters, optimized applications, and AI-powered message generation.
          </p>
          <Link
            href="/resumes/upload"
            className="btn-gradient inline-block mt-5 px-6 py-2.5 text-sm font-medium rounded-lg"
          >
            Upload Your First Resume
          </Link>
        </div>
      ) : (
        <div className="space-y-2 stagger-children">
          {resumes.map((resume) => (
            <div
              key={resume.id}
              className={`card-elevated p-4 ${
                resume.is_active
                  ? "border-accent/50 bg-accent/5 glow-accent"
                  : ""
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="space-y-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/resumes/${resume.id}`}
                      className="text-sm font-medium hover:underline truncate"
                    >
                      {resume.title}
                    </Link>
                    {resume.is_active && (
                      <span className="text-[10px] font-medium px-1.5 py-0.5 bg-accent/10 text-accent rounded">
                        Active
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    {resume.profile_classification?.profile_type && (
                      <span>{resume.profile_classification.profile_type}</span>
                    )}
                    {resume.profile_classification?.seniority && (
                      <span>{resume.profile_classification.seniority}</span>
                    )}
                    {resume.extracted_info?.years_experience && (
                      <span>{resume.extracted_info.years_experience}</span>
                    )}
                  </div>
                  {resume.extracted_info?.skills?.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {resume.extracted_info.skills.slice(0, 8).map((skill) => (
                        <span
                          key={skill}
                          className="text-[10px] px-1.5 py-0.5 bg-muted rounded text-muted-foreground"
                        >
                          {skill}
                        </span>
                      ))}
                      {resume.extracted_info.skills.length > 8 && (
                        <span className="text-[10px] text-muted-foreground">
                          +{resume.extracted_info.skills.length - 8} more
                        </span>
                      )}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {!resume.is_active && (
                    <button
                      onClick={() => handleSetActive(resume.id)}
                      className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                      Set Active
                    </button>
                  )}
                  <button
                    onClick={() => setDeleteTarget(resume)}
                    className="text-xs text-muted-foreground hover:text-destructive transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete confirmation modal */}
      {deleteTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          onClick={() => setDeleteTarget(null)}
        >
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
          <div
            className="relative bg-background border border-border rounded-xl p-6 w-full max-w-sm mx-4 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-base font-semibold">Delete resume</h3>
            <p className="text-sm text-muted-foreground mt-2">
              Are you sure you want to delete{" "}
              <span className="text-foreground font-medium">
                {deleteTarget.title}
              </span>
              ? This will permanently remove the resume and its PDF. This action
              cannot be undone.
            </p>
            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setDeleteTarget(null)}
                className="px-4 py-2 text-sm rounded-lg border border-border hover:bg-muted transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                disabled={deleting}
                className="px-4 py-2 text-sm rounded-lg bg-destructive text-destructive-foreground hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {deleting ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
