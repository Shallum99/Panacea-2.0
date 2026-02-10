"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { getResume, setActiveResume, type Resume } from "@/lib/api/resumes";
import Link from "next/link";

export default function ResumeDetailPage() {
  const params = useParams();
  const router = useRouter();
  const [resume, setResume] = useState<Resume | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (params.id) {
      loadResume(Number(params.id));
    }
  }, [params.id]);

  async function loadResume(id: number) {
    try {
      const data = await getResume(id);
      setResume(data);
    } catch {
      toast.error("Resume not found");
      router.push("/resumes");
    } finally {
      setLoading(false);
    }
  }

  async function handleSetActive() {
    if (!resume) return;
    try {
      const updated = await setActiveResume(resume.id);
      setResume(updated);
      toast.success("Set as active resume");
    } catch {
      toast.error("Failed to update");
    }
  }

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-6 bg-muted rounded w-1/3" />
        <div className="h-4 bg-muted rounded w-1/2" />
        <div className="h-40 bg-muted rounded" />
      </div>
    );
  }

  if (!resume) return null;

  const info = resume.extracted_info;
  const profile = resume.profile_classification;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight">
              {resume.title}
            </h1>
            {resume.is_active && (
              <span className="text-[10px] font-medium px-1.5 py-0.5 bg-accent/10 text-accent rounded">
                Active
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            {info.name} &middot; {profile.profile_type} &middot;{" "}
            {profile.seniority}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {!resume.is_active && (
            <button
              onClick={handleSetActive}
              className="px-3 py-1.5 text-xs border border-border rounded-lg hover:bg-muted transition-colors"
            >
              Set Active
            </button>
          )}
          <Link
            href="/resumes"
            className="px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Back
          </Link>
        </div>
      </div>

      {/* Info grid */}
      <div className="grid grid-cols-2 gap-4">
        <InfoCard label="Email" value={info.email} />
        <InfoCard label="Phone" value={info.phone} />
        <InfoCard label="Education" value={info.education} />
        <InfoCard label="Experience" value={info.years_experience} />
        <InfoCard label="Recent Role" value={info.recent_job} />
        <InfoCard label="Recent Company" value={info.recent_company} />
        <InfoCard label="Industry" value={profile.industry_focus} />
        <InfoCard
          label="Languages"
          value={profile.primary_languages?.join(", ")}
        />
      </div>

      {/* Skills */}
      {info.skills?.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-medium">Skills</h2>
          <div className="flex flex-wrap gap-1.5">
            {info.skills.map((skill) => (
              <span
                key={skill}
                className="text-xs px-2 py-1 bg-muted rounded text-muted-foreground"
              >
                {skill}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Frameworks */}
      {profile.frameworks?.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-medium">Frameworks</h2>
          <div className="flex flex-wrap gap-1.5">
            {profile.frameworks.map((fw) => (
              <span
                key={fw}
                className="text-xs px-2 py-1 bg-muted rounded text-muted-foreground"
              >
                {fw}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function InfoCard({ label, value }: { label: string; value?: string }) {
  return (
    <div className="border border-border rounded-lg p-3">
      <p className="text-[10px] text-muted-foreground uppercase tracking-wider">
        {label}
      </p>
      <p className="text-sm mt-0.5 truncate">{value || "—"}</p>
    </div>
  );
}
