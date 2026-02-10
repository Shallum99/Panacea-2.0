"use client";

import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { uploadResume } from "@/lib/api/resumes";

export default function ResumeUploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [makeActive, setMakeActive] = useState(true);
  const [uploading, setUploading] = useState(false);
  const router = useRouter();

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const pdf = acceptedFiles[0];
    if (pdf) {
      setFile(pdf);
      if (!title) {
        setTitle(pdf.name.replace(".pdf", "").replace(/[-_]/g, " "));
      }
    }
  }, [title]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    maxFiles: 1,
    maxSize: 10 * 1024 * 1024, // 10MB
  });

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !title.trim()) return;

    setUploading(true);
    try {
      await uploadResume(file, title.trim(), makeActive);
      toast.success("Resume uploaded and analyzed");
      router.push("/resumes");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to upload resume";
      toast.error(message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="max-w-xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Upload Resume</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Upload a PDF to create a new resume profile
        </p>
      </div>

      <form onSubmit={handleUpload} className="space-y-5">
        {/* Dropzone */}
        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-lg p-10 text-center cursor-pointer transition-colors ${
            isDragActive
              ? "border-accent bg-accent/5"
              : file
              ? "border-success/50 bg-success/5"
              : "border-border hover:border-muted-foreground"
          }`}
        >
          <input {...getInputProps()} />
          {file ? (
            <div className="space-y-1">
              <p className="text-sm font-medium">{file.name}</p>
              <p className="text-xs text-muted-foreground">
                {(file.size / 1024 / 1024).toFixed(2)} MB — Click or drop to
                replace
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">
                {isDragActive
                  ? "Drop your PDF here"
                  : "Drag and drop a PDF, or click to browse"}
              </p>
              <p className="text-xs text-muted-foreground/60">Max 10MB</p>
            </div>
          )}
        </div>

        {/* Title */}
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Profile Name</label>
          <input
            type="text"
            placeholder="e.g. Backend Developer Resume"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            className="w-full px-3 py-2 bg-muted border border-border rounded-lg text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>

        {/* Make active */}
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={makeActive}
            onChange={(e) => setMakeActive(e.target.checked)}
            className="rounded border-border"
          />
          <span className="text-muted-foreground">
            Set as active resume profile
          </span>
        </label>

        {/* Submit */}
        <button
          type="submit"
          disabled={!file || !title.trim() || uploading}
          className="w-full py-2.5 bg-accent text-accent-foreground text-sm font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {uploading ? "Uploading & Analyzing..." : "Upload Resume"}
        </button>
      </form>
    </div>
  );
}
