"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { toast } from "sonner";
import Link from "next/link";
import {
  getProfile,
  updateProfile,
  getWritingSamples,
  createWritingSample,
  deleteWritingSample,
  type Profile,
  type WritingSample,
} from "@/lib/api/profile";
import {
  getResumes,
  setActiveResume,
  deleteResume,
  type Resume,
} from "@/lib/api/resumes";

// --- Tag Input Component ---
function TagInput({
  tags,
  onChange,
  placeholder,
}: {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
}) {
  const [input, setInput] = useState("");

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && input.trim()) {
      e.preventDefault();
      if (!tags.includes(input.trim())) {
        onChange([...tags, input.trim()]);
      }
      setInput("");
    }
    if (e.key === "Backspace" && !input && tags.length > 0) {
      onChange(tags.slice(0, -1));
    }
  }

  return (
    <div className="flex flex-wrap gap-1.5 p-2 border border-border rounded-lg bg-background min-h-[42px] focus-within:ring-1 focus-within:ring-accent">
      {tags.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-accent/10 text-accent border border-accent/20 rounded-md"
        >
          {tag}
          <button
            type="button"
            onClick={() => onChange(tags.filter((t) => t !== tag))}
            className="text-accent/60 hover:text-accent"
          >
            x
          </button>
        </span>
      ))}
      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={tags.length === 0 ? placeholder : ""}
        className="flex-1 min-w-[120px] bg-transparent text-sm outline-none placeholder:text-muted-foreground/50"
      />
    </div>
  );
}

// --- Toggle Group ---
function ToggleGroup({
  options,
  value,
  onChange,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex gap-1.5">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-3 py-1.5 text-xs rounded-md border transition-colors ${
            value === opt.value
              ? "border-accent bg-accent/10 text-accent"
              : "border-border text-muted-foreground hover:text-foreground"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [samples, setSamples] = useState<WritingSample[]>([]);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);

  // Writing sample form
  const [newSampleTitle, setNewSampleTitle] = useState("");
  const [newSampleContent, setNewSampleContent] = useState("");
  const [newSampleType, setNewSampleType] = useState("email");
  const [showSampleForm, setShowSampleForm] = useState(false);

  // Delete confirmation
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [confirmResumeDelete, setConfirmResumeDelete] = useState<number | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [p, s, r] = await Promise.all([
          getProfile(),
          getWritingSamples(),
          getResumes(),
        ]);
        setProfile(p);
        setSamples(s);
        setResumes(r);
      } catch {
        toast.error("Failed to load profile");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const saveSection = useCallback(
    async (section: string, data: Partial<Profile>) => {
      setSaving(section);
      try {
        const updated = await updateProfile(data);
        setProfile(updated);
        toast.success("Saved");
      } catch {
        toast.error("Failed to save");
      } finally {
        setSaving(null);
      }
    },
    []
  );

  // Auto-save tone on change
  const toneTimeout = useRef<ReturnType<typeof setTimeout>>(undefined);
  function handleToneChange(key: string, value: string) {
    if (!profile) return;
    const updated = { ...profile, [key]: value };
    setProfile(updated);
    clearTimeout(toneTimeout.current);
    toneTimeout.current = setTimeout(() => {
      saveSection("tone", {
        tone_formality: updated.tone_formality,
        tone_confidence: updated.tone_confidence,
        tone_verbosity: updated.tone_verbosity,
      });
    }, 300);
  }

  async function handleAddSample() {
    if (!newSampleContent.trim()) return;
    setSaving("sample-add");
    try {
      const s = await createWritingSample({
        title: newSampleTitle || undefined,
        content: newSampleContent,
        sample_type: newSampleType,
      });
      setSamples((prev) => [s, ...prev]);
      setNewSampleTitle("");
      setNewSampleContent("");
      setShowSampleForm(false);
      toast.success("Writing sample added");
    } catch {
      toast.error("Failed to add sample");
    } finally {
      setSaving(null);
    }
  }

  async function handleDeleteSample(id: number) {
    try {
      await deleteWritingSample(id);
      setSamples((prev) => prev.filter((s) => s.id !== id));
      setConfirmDelete(null);
      toast.success("Sample deleted");
    } catch {
      toast.error("Failed to delete");
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

  async function handleDeleteResume(id: number) {
    try {
      await deleteResume(id);
      setResumes((prev) => prev.filter((r) => r.id !== id));
      setConfirmResumeDelete(null);
      toast.success("Resume deleted");
    } catch {
      toast.error("Failed to delete resume");
    }
  }

  if (loading || !profile) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Profile</h1>
        </div>
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="border border-border rounded-lg p-6 animate-pulse space-y-4"
          >
            <div className="h-4 bg-muted rounded w-1/4" />
            <div className="h-10 bg-muted rounded w-full" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Profile</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Your profile powers personalized message generation. Upload a resume
          to auto-fill.
        </p>
      </div>

      {/* 1. Personal Details */}
      <section className="space-y-4">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Personal Details
        </h2>
        <div className="border border-border rounded-lg p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground">Full Name</label>
              <input
                value={profile.full_name || ""}
                onChange={(e) =>
                  setProfile({ ...profile, full_name: e.target.value })
                }
                className="w-full mt-1 px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-accent"
                placeholder="John Doe"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">
                Email{" "}
                <span className="text-muted-foreground/50">(from account)</span>
              </label>
              <input
                value={profile.email}
                disabled
                className="w-full mt-1 px-3 py-2 text-sm border border-border rounded-lg bg-muted/30 text-muted-foreground"
              />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-muted-foreground">Phone</label>
              <input
                value={profile.phone || ""}
                onChange={(e) =>
                  setProfile({ ...profile, phone: e.target.value })
                }
                className="w-full mt-1 px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-accent"
                placeholder="+1 (555) 123-4567"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">
                LinkedIn URL
              </label>
              <input
                value={profile.linkedin_url || ""}
                onChange={(e) =>
                  setProfile({ ...profile, linkedin_url: e.target.value })
                }
                className="w-full mt-1 px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-accent"
                placeholder="linkedin.com/in/johndoe"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">
                Portfolio / GitHub
              </label>
              <input
                value={profile.portfolio_url || ""}
                onChange={(e) =>
                  setProfile({ ...profile, portfolio_url: e.target.value })
                }
                className="w-full mt-1 px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-accent"
                placeholder="github.com/johndoe"
              />
            </div>
          </div>
          <div className="flex justify-end">
            <button
              onClick={() =>
                saveSection("personal", {
                  full_name: profile.full_name,
                  phone: profile.phone,
                  linkedin_url: profile.linkedin_url,
                  portfolio_url: profile.portfolio_url,
                })
              }
              disabled={saving === "personal"}
              className="px-4 py-1.5 text-xs font-medium bg-accent text-accent-foreground rounded-md hover:opacity-90 disabled:opacity-40"
            >
              {saving === "personal" ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </section>

      {/* 2. Professional Summary */}
      <section className="space-y-4">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Professional Summary
        </h2>
        <div className="border border-border rounded-lg p-4 space-y-3">
          <textarea
            value={profile.professional_summary || ""}
            onChange={(e) =>
              setProfile({ ...profile, professional_summary: e.target.value })
            }
            rows={4}
            className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-accent resize-none"
            placeholder="A brief elevator pitch about who you are and what you bring. The AI will reference this when generating messages."
          />
          <div className="flex justify-end">
            <button
              onClick={() =>
                saveSection("summary", {
                  professional_summary: profile.professional_summary,
                })
              }
              disabled={saving === "summary"}
              className="px-4 py-1.5 text-xs font-medium bg-accent text-accent-foreground rounded-md hover:opacity-90 disabled:opacity-40"
            >
              {saving === "summary" ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </section>

      {/* 3. Master Skills */}
      <section className="space-y-4">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Skills
        </h2>
        <div className="border border-border rounded-lg p-4 space-y-3">
          <TagInput
            tags={profile.master_skills || []}
            onChange={(tags) =>
              setProfile({ ...profile, master_skills: tags })
            }
            placeholder="Type a skill and press Enter"
          />
          <div className="flex justify-end">
            <button
              onClick={() =>
                saveSection("skills", {
                  master_skills: profile.master_skills,
                })
              }
              disabled={saving === "skills"}
              className="px-4 py-1.5 text-xs font-medium bg-accent text-accent-foreground rounded-md hover:opacity-90 disabled:opacity-40"
            >
              {saving === "skills" ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </section>

      {/* 4. Job Preferences */}
      <section className="space-y-4">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Job Preferences
        </h2>
        <div className="border border-border rounded-lg p-4 space-y-4">
          <div>
            <label className="text-xs text-muted-foreground">Target Roles</label>
            <div className="mt-1">
              <TagInput
                tags={profile.target_roles || []}
                onChange={(tags) =>
                  setProfile({ ...profile, target_roles: tags })
                }
                placeholder="e.g. Senior Frontend Engineer"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Industries</label>
            <div className="mt-1">
              <TagInput
                tags={profile.target_industries || []}
                onChange={(tags) =>
                  setProfile({ ...profile, target_industries: tags })
                }
                placeholder="e.g. Fintech, SaaS"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Locations</label>
            <div className="mt-1">
              <TagInput
                tags={profile.target_locations || []}
                onChange={(tags) =>
                  setProfile({ ...profile, target_locations: tags })
                }
                placeholder="e.g. San Francisco, Remote"
              />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-muted-foreground">
                Work Arrangement
              </label>
              <select
                value={profile.work_arrangement || ""}
                onChange={(e) =>
                  setProfile({
                    ...profile,
                    work_arrangement: e.target.value || null,
                  })
                }
                className="w-full mt-1 px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-accent"
              >
                <option value="">Not set</option>
                <option value="remote">Remote</option>
                <option value="hybrid">Hybrid</option>
                <option value="onsite">On-site</option>
                <option value="flexible">Flexible</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">
                Min Salary ($)
              </label>
              <input
                type="number"
                value={
                  profile.salary_range_min
                    ? profile.salary_range_min / 100
                    : ""
                }
                onChange={(e) =>
                  setProfile({
                    ...profile,
                    salary_range_min: e.target.value
                      ? Number(e.target.value) * 100
                      : null,
                  })
                }
                className="w-full mt-1 px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-accent"
                placeholder="80,000"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">
                Max Salary ($)
              </label>
              <input
                type="number"
                value={
                  profile.salary_range_max
                    ? profile.salary_range_max / 100
                    : ""
                }
                onChange={(e) =>
                  setProfile({
                    ...profile,
                    salary_range_max: e.target.value
                      ? Number(e.target.value) * 100
                      : null,
                  })
                }
                className="w-full mt-1 px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-accent"
                placeholder="150,000"
              />
            </div>
          </div>
          <div className="flex justify-end">
            <button
              onClick={() =>
                saveSection("prefs", {
                  target_roles: profile.target_roles,
                  target_industries: profile.target_industries,
                  target_locations: profile.target_locations,
                  work_arrangement: profile.work_arrangement,
                  salary_range_min: profile.salary_range_min,
                  salary_range_max: profile.salary_range_max,
                })
              }
              disabled={saving === "prefs"}
              className="px-4 py-1.5 text-xs font-medium bg-accent text-accent-foreground rounded-md hover:opacity-90 disabled:opacity-40"
            >
              {saving === "prefs" ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </section>

      {/* 5. Tone Settings */}
      <section className="space-y-4">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Tone Settings
        </h2>
        <div className="border border-border rounded-lg p-4 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Formality</p>
              <p className="text-xs text-muted-foreground">
                How professional should messages sound?
              </p>
            </div>
            <ToggleGroup
              options={[
                { value: "formal", label: "Formal" },
                { value: "balanced", label: "Balanced" },
                { value: "casual", label: "Casual" },
              ]}
              value={profile.tone_formality}
              onChange={(v) => handleToneChange("tone_formality", v)}
            />
          </div>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Confidence</p>
              <p className="text-xs text-muted-foreground">
                How assertive should the writing be?
              </p>
            </div>
            <ToggleGroup
              options={[
                { value: "humble", label: "Humble" },
                { value: "balanced", label: "Balanced" },
                { value: "confident", label: "Confident" },
              ]}
              value={profile.tone_confidence}
              onChange={(v) => handleToneChange("tone_confidence", v)}
            />
          </div>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Length</p>
              <p className="text-xs text-muted-foreground">
                How much detail should messages include?
              </p>
            </div>
            <ToggleGroup
              options={[
                { value: "concise", label: "Concise" },
                { value: "balanced", label: "Balanced" },
                { value: "detailed", label: "Detailed" },
              ]}
              value={profile.tone_verbosity}
              onChange={(v) => handleToneChange("tone_verbosity", v)}
            />
          </div>
          <p className="text-[10px] text-muted-foreground/60">
            Changes save automatically
          </p>
        </div>
      </section>

      {/* 6. Writing Samples */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
            Writing Samples
          </h2>
          <button
            onClick={() => setShowSampleForm(!showSampleForm)}
            className="px-3 py-1 text-xs font-medium text-accent border border-accent/30 rounded-md hover:bg-accent/10"
          >
            {showSampleForm ? "Cancel" : "Add Sample"}
          </button>
        </div>
        <div className="border border-border rounded-lg divide-y divide-border">
          {showSampleForm && (
            <div className="p-4 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <input
                  value={newSampleTitle}
                  onChange={(e) => setNewSampleTitle(e.target.value)}
                  placeholder="Title (optional)"
                  className="px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-accent"
                />
                <select
                  value={newSampleType}
                  onChange={(e) => setNewSampleType(e.target.value)}
                  className="px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-accent"
                >
                  <option value="email">Email</option>
                  <option value="linkedin">LinkedIn</option>
                  <option value="cover_letter">Cover Letter</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <textarea
                value={newSampleContent}
                onChange={(e) => setNewSampleContent(e.target.value)}
                rows={5}
                placeholder="Paste a message you've written that represents your voice and style..."
                className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-accent resize-none"
              />
              <div className="flex justify-end">
                <button
                  onClick={handleAddSample}
                  disabled={
                    !newSampleContent.trim() || saving === "sample-add"
                  }
                  className="px-4 py-1.5 text-xs font-medium bg-accent text-accent-foreground rounded-md hover:opacity-90 disabled:opacity-40"
                >
                  {saving === "sample-add" ? "Adding..." : "Add"}
                </button>
              </div>
            </div>
          )}

          {samples.length === 0 && !showSampleForm && (
            <div className="px-4 py-8 text-center">
              <p className="text-sm text-muted-foreground">
                No writing samples yet. Add examples of your emails or messages
                so the AI can match your voice.
              </p>
            </div>
          )}

          {samples.map((sample) => (
            <div key={sample.id} className="px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    {sample.title && (
                      <p className="text-sm font-medium">{sample.title}</p>
                    )}
                    {sample.sample_type && (
                      <span className="text-[10px] px-1.5 py-0.5 bg-muted rounded text-muted-foreground">
                        {sample.sample_type}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-3 whitespace-pre-wrap">
                    {sample.content}
                  </p>
                </div>
                {confirmDelete === sample.id ? (
                  <div className="flex gap-1.5 shrink-0">
                    <button
                      onClick={() => handleDeleteSample(sample.id)}
                      className="px-2 py-1 text-[10px] text-destructive border border-destructive/30 rounded hover:bg-destructive/10"
                    >
                      Confirm
                    </button>
                    <button
                      onClick={() => setConfirmDelete(null)}
                      className="px-2 py-1 text-[10px] text-muted-foreground border border-border rounded hover:bg-muted"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setConfirmDelete(sample.id)}
                    className="text-xs text-muted-foreground hover:text-destructive shrink-0"
                  >
                    Delete
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 7. Resumes */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
            Resumes
          </h2>
          <Link
            href="/resumes/upload"
            className="px-3 py-1 text-xs font-medium text-accent border border-accent/30 rounded-md hover:bg-accent/10"
          >
            Upload Resume
          </Link>
        </div>
        <div className="border border-border rounded-lg divide-y divide-border">
          {resumes.length === 0 && (
            <div className="px-4 py-8 text-center">
              <p className="text-sm text-muted-foreground">
                No resumes yet.{" "}
                <Link href="/resumes/upload" className="text-accent underline">
                  Upload one
                </Link>{" "}
                to auto-fill your profile.
              </p>
            </div>
          )}

          {resumes.map((resume) => (
            <div
              key={resume.id}
              className="flex items-center justify-between px-4 py-3"
            >
              <div className="flex items-center gap-3 min-w-0">
                <Link
                  href={`/resumes/${resume.id}`}
                  className="text-sm font-medium hover:text-accent truncate"
                >
                  {resume.title}
                </Link>
                {resume.is_active && (
                  <span className="text-[10px] px-1.5 py-0.5 bg-accent/10 text-accent border border-accent/20 rounded shrink-0">
                    Active
                  </span>
                )}
                {resume.profile_classification?.profile_type && (
                  <span className="text-[10px] text-muted-foreground shrink-0">
                    {resume.profile_classification.profile_type}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {!resume.is_active && (
                  <button
                    onClick={() => handleSetActive(resume.id)}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    Set Active
                  </button>
                )}
                {confirmResumeDelete === resume.id ? (
                  <div className="flex gap-1.5">
                    <button
                      onClick={() => handleDeleteResume(resume.id)}
                      className="px-2 py-1 text-[10px] text-destructive border border-destructive/30 rounded hover:bg-destructive/10"
                    >
                      Confirm
                    </button>
                    <button
                      onClick={() => setConfirmResumeDelete(null)}
                      className="px-2 py-1 text-[10px] text-muted-foreground border border-border rounded hover:bg-muted"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setConfirmResumeDelete(resume.id)}
                    className="text-xs text-muted-foreground hover:text-destructive"
                  >
                    Delete
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
