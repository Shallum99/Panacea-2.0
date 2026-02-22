"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  ArrowLeft,
  ArrowUp,
  Loader2,
  FileText,
  MessageSquare,
  Download,
  Check,
  AlertTriangle,
  Clock,
  ChevronDown,
} from "lucide-react";
import Link from "next/link";
import { getResume, getResumePdfUrl, type Resume, type EditChange } from "@/lib/api/resumes";
import { createClient } from "@/lib/supabase/client";
import {
  useResumeEditor,
  type DraftEdit,
  type EditHistoryItem,
} from "@/hooks/useResumeEditor";
import FieldMapView from "@/components/resume-editor/FieldMapView";
import DraftBanner from "@/components/resume-editor/DraftBanner";

type RightTab = "fields" | "preview";

export default function ResumeEditorPage() {
  const params = useParams();
  const router = useRouter();
  const resumeId = Number(params.id);

  const [resume, setResume] = useState<Resume | null>(null);
  const [resumeLoading, setResumeLoading] = useState(true);
  const [rightTab, setRightTab] = useState<RightTab>("fields");

  const editor = useResumeEditor(resumeId);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Load resume metadata
  useEffect(() => {
    if (!resumeId) return;
    (async () => {
      try {
        const data = await getResume(resumeId);
        setResume(data);
      } catch {
        toast.error("Resume not found");
        router.push("/resumes");
      } finally {
        setResumeLoading(false);
      }
    })();
  }, [resumeId, router]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height =
        Math.min(textareaRef.current.scrollHeight, 160) + "px";
    }
  }, [editor.input]);

  // Handle send prompt
  async function handleSend() {
    if (!editor.input.trim() || editor.sending) return;
    const result = await editor.submitEdit();
    if (result) {
      if (result.changes.length > 0) {
        toast.success(
          `v${result.version_number}: ${result.changes.length} changes applied`
        );
        setRightTab("preview");
      } else {
        toast.info("No changes were needed for that request.");
      }
    }
  }

  // Handle quick prompt click
  async function handleQuickPrompt(prompt: string) {
    editor.setInput(prompt);
    const result = await editor.submitEdit(prompt);
    if (result) {
      if (result.changes.length > 0) {
        toast.success(
          `v${result.version_number}: ${result.changes.length} changes applied`
        );
        setRightTab("preview");
      } else {
        toast.info("No changes were needed for that request.");
      }
    }
  }

  // Handle apply drafts
  async function handleApplyDrafts() {
    const result = await editor.applyDrafts();
    if (result && result.changes.length > 0) {
      toast.success(
        `v${result.version_number}: ${result.changes.length} changes applied`
      );
      setRightTab("preview");
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  if (resumeLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!resume) return null;

  const latestVersion =
    editor.versions.length > 0
      ? editor.versions[editor.versions.length - 1]
      : null;

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border shrink-0">
        <div className="flex items-center gap-3">
          <Link
            href={`/resumes/${resumeId}`}
            className="p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <h1 className="text-sm font-medium">{resume.title}</h1>
            <p className="text-[10px] text-muted-foreground">
              Resume Editor
              {editor.formMap &&
                ` \u00B7 ${editor.formMap.editable_fields} editable fields`}
              {editor.currentVersion &&
                ` \u00B7 v${editor.currentVersion}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {editor.versions.length > 0 && (
            <DownloadDropdown
              versions={editor.versions}
              getVersionPdfUrl={editor.getVersionPdfUrl}
            />
          )}
        </div>
      </div>

      {/* Main content: split view */}
      <div className="flex flex-1 min-h-0">
        {/* Left panel: Edit History + Prompt */}
        <div className="flex flex-col flex-1 min-w-0 border-r border-border">
          {/* Edit history */}
          <div
            className="flex-1 overflow-y-auto px-4 py-4 space-y-4"
            onScroll={editor.handleScroll}
          >
            {editor.editHistory.length === 0 && !editor.sending && (
              <WelcomeScreen
                fontQuality={editor.formMap?.font_quality}
                editableFields={editor.formMap?.editable_fields}
                onPromptClick={handleQuickPrompt}
              />
            )}
            {editor.editHistory.length === 0 && editor.sending && (
              <div className="flex items-center justify-center h-full">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Applying edits...
                </div>
              </div>
            )}
            {editor.editHistory.map((item, idx) => (
              <EditHistoryEntry
                key={idx}
                item={item}
                onVersionClick={() => {
                  editor.switchToVersion(item.versionNumber);
                  setRightTab("preview");
                }}
              />
            ))}
            {editor.sending && editor.editHistory.length > 0 && (
              <div className="flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Applying edits...
              </div>
            )}
            {editor.editError && (
              <div className="px-3 py-2 rounded-lg border border-red-500/20 bg-red-500/5 text-xs text-red-400">
                {editor.editError}
              </div>
            )}
            <div ref={editor.messagesEndRef} />
          </div>

          {/* Draft banner */}
          <DraftBanner
            draftCount={editor.draftCount}
            isGenerating={editor.sending}
            hasGenerated={editor.versions.length > 0}
            onGenerate={handleApplyDrafts}
            onClearAll={editor.clearDrafts}
            onViewChanges={() => setRightTab("fields")}
          />

          {/* Input */}
          <div className="px-4 py-3 border-t border-border">
            <div className="flex items-end gap-2">
              <textarea
                ref={textareaRef}
                value={editor.input}
                onChange={(e) => editor.setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Edit my experience bullets to be more technical..."
                className="flex-1 resize-none bg-muted rounded-lg px-3 py-2 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-accent min-h-[36px] max-h-[160px]"
                rows={1}
              />
              <button
                onClick={handleSend}
                disabled={!editor.input.trim() || editor.sending}
                className="shrink-0 p-2 rounded-lg bg-accent text-accent-foreground hover:bg-accent/90 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              >
                {editor.sending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <ArrowUp className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Right panel: Fields / Preview */}
        <div className="flex flex-col w-[400px] shrink-0">
          {/* Tabs */}
          <div className="flex border-b border-border">
            <TabButton
              active={rightTab === "fields"}
              onClick={() => setRightTab("fields")}
              icon={<FileText className="w-3.5 h-3.5" />}
              label="Fields"
              badge={editor.draftCount > 0 ? editor.draftCount : undefined}
            />
            <TabButton
              active={rightTab === "preview"}
              onClick={() => setRightTab("preview")}
              icon={<FileText className="w-3.5 h-3.5" />}
              label="Preview"
              badge={
                editor.versions.length > 0
                  ? editor.versions.length
                  : undefined
              }
            />
          </div>

          {/* Tab content */}
          <div className="flex-1 min-h-0 overflow-hidden">
            {rightTab === "fields" && (
              <>
                {editor.formMapLoading ? (
                  <div className="flex items-center justify-center h-full">
                    <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                  </div>
                ) : editor.formMap ? (
                  <FieldMapView
                    formMap={editor.formMap}
                    drafts={editor.drafts}
                    onRemoveDraft={editor.removeDraft}
                  />
                ) : (
                  <div className="flex flex-col items-center justify-center h-full text-center px-6">
                    <FileText className="w-8 h-8 text-muted-foreground mb-2" />
                    <p className="text-sm text-muted-foreground">
                      {editor.formMapError ||
                        "Could not load resume fields."}
                    </p>
                    <button
                      onClick={() => editor.reloadFormMap()}
                      className="mt-2 text-xs text-accent hover:underline"
                    >
                      Retry
                    </button>
                  </div>
                )}
              </>
            )}
            {rightTab === "preview" && (
              <PdfPreview
                resumeId={resumeId}
                versions={editor.versions}
                currentVersion={editor.currentVersion}
                onVersionSwitch={editor.switchToVersion}
                getVersionPdfUrl={editor.getVersionPdfUrl}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ──

function TabButton({
  active,
  onClick,
  icon,
  label,
  badge,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  badge?: number;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-colors border-b-2 ${
        active
          ? "border-accent text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground"
      }`}
    >
      {icon}
      {label}
      {badge != null && badge > 0 && (
        <span className="ml-1 px-1.5 py-0.5 text-[10px] rounded-full bg-accent/10 text-accent">
          {badge}
        </span>
      )}
    </button>
  );
}

// ── Edit History Entry ──

function EditHistoryEntry({
  item,
  onVersionClick,
}: {
  item: EditHistoryItem;
  onVersionClick: () => void;
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="space-y-2">
      {/* User prompt bubble */}
      <div className="flex justify-end">
        <div className="max-w-[85%] px-3 py-2 rounded-lg bg-accent/10 text-xs leading-relaxed">
          {item.prompt}
        </div>
      </div>

      {/* Result */}
      <div className="max-w-[85%]">
        <div className="rounded-lg border border-border bg-background overflow-hidden">
          {/* Header */}
          <div className="px-3 py-2 border-b border-border flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Check className="w-3.5 h-3.5 text-green-500" />
              <span className="text-xs font-medium">
                v{item.versionNumber}
              </span>
              <span className="text-[10px] text-muted-foreground">
                {item.changes.length}{" "}
                {item.changes.length === 1 ? "change" : "changes"}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={onVersionClick}
                className="text-[10px] text-accent hover:underline"
              >
                Preview
              </button>
              <button
                onClick={() => setExpanded(!expanded)}
                className="p-0.5 text-muted-foreground hover:text-foreground"
              >
                <ChevronDown
                  className={`w-3.5 h-3.5 transition-transform ${
                    expanded ? "" : "-rotate-90"
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Changes list */}
          {expanded && item.changes.length > 0 && (
            <div className="divide-y divide-border">
              {item.changes.map((change, ci) => (
                <ChangeItem key={ci} change={change} />
              ))}
            </div>
          )}

          {expanded && item.changes.length === 0 && (
            <div className="px-3 py-2 text-xs text-muted-foreground">
              No changes were needed.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Single Change Item ──

function ChangeItem({ change }: { change: EditChange }) {
  return (
    <div className="px-3 py-2 space-y-1">
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] font-mono text-muted-foreground bg-muted px-1 py-0.5 rounded">
          {change.field_id}
        </span>
        {change.section && (
          <span className="text-[10px] text-muted-foreground">
            {change.section}
          </span>
        )}
      </div>
      <p className="text-[11px] text-muted-foreground line-through leading-relaxed">
        {change.original_text.length > 120
          ? change.original_text.slice(0, 120) + "..."
          : change.original_text}
      </p>
      <p className="text-[11px] text-foreground leading-relaxed">
        {change.new_text.length > 120
          ? change.new_text.slice(0, 120) + "..."
          : change.new_text}
      </p>
      {change.reasoning && (
        <p className="text-[10px] text-muted-foreground italic">
          {change.reasoning}
        </p>
      )}
    </div>
  );
}

// ── Quick Prompts ──

const QUICK_PROMPTS = [
  "Make my experience bullets more impactful",
  "Add more quantitative metrics to my bullets",
  "Make my skills section more technical",
  "Rewrite bullets to emphasize leadership",
];

function WelcomeScreen({
  fontQuality,
  editableFields,
  onPromptClick,
}: {
  fontQuality?: string;
  editableFields?: number;
  onPromptClick?: (prompt: string) => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-6">
      <MessageSquare className="w-10 h-10 text-muted-foreground mb-3" />
      <h2 className="text-sm font-medium mb-1">Resume Editor</h2>
      <p className="text-xs text-muted-foreground max-w-sm leading-relaxed">
        Tell me what to change and I&apos;ll edit your PDF directly. Each edit
        creates a new version you can preview and download.
      </p>
      {editableFields != null && (
        <p className="text-[10px] text-muted-foreground mt-3">
          {editableFields} editable fields detected
          {fontQuality && (
            <span
              className={
                fontQuality === "good" ? "text-green-500" : "text-yellow-500"
              }
            >
              {" "}
              &middot; {fontQuality} fonts
            </span>
          )}
        </p>
      )}
      <div className="mt-5 flex flex-wrap justify-center gap-2">
        {QUICK_PROMPTS.map((p) => (
          <button
            key={p}
            onClick={() => onPromptClick?.(p)}
            className="px-3 py-1.5 text-[11px] rounded-full border border-border text-muted-foreground hover:border-accent hover:text-accent transition-colors cursor-pointer"
          >
            {p}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── PDF Preview with Version Selector ──

function PdfPreview({
  resumeId,
  versions,
  currentVersion,
  onVersionSwitch,
  getVersionPdfUrl,
}: {
  resumeId: number;
  versions: Array<{
    version_number: number;
    download_id: string;
    diff_download_id: string | null;
    prompt_used: string;
  }>;
  currentVersion: number | null;
  onVersionSwitch: (v: number | null) => void;
  getVersionPdfUrl: (downloadId: string) => string;
}) {
  const [showDiff, setShowDiff] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const activeVersion = versions.find(
    (v) => v.version_number === currentVersion
  );

  const activeDownloadId = activeVersion
    ? showDiff && activeVersion.diff_download_id
      ? activeVersion.diff_download_id
      : activeVersion.download_id
    : null;

  useEffect(() => {
    if (!activeDownloadId) {
      setPdfUrl(null);
      return;
    }

    setLoading(true);
    const url = getVersionPdfUrl(activeDownloadId);

    (async () => {
      try {
        let token: string | null = null;
        if (process.env.NEXT_PUBLIC_DEV_MODE !== "true") {
          const supabase = createClient();
          const {
            data: { session },
          } = await supabase.auth.getSession();
          token = session?.access_token ?? null;
        }
        const res = await fetch(url, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) throw new Error("Failed to fetch PDF");
        const blob = await res.blob();
        const blobUrl = URL.createObjectURL(blob);
        setPdfUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return blobUrl;
        });
      } catch {
        setPdfUrl(null);
      } finally {
        setLoading(false);
      }
    })();

    return () => {};
  }, [activeDownloadId, getVersionPdfUrl]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    };
  }, []);

  if (versions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6">
        <FileText className="w-8 h-8 text-muted-foreground mb-2" />
        <p className="text-xs text-muted-foreground">
          Enter a prompt to create your first edit version.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Version selector + diff toggle */}
      <div className="flex items-center justify-between border-b border-border px-2 py-1.5">
        <div className="flex items-center gap-1 overflow-x-auto">
          {versions.map((v) => (
            <button
              key={v.version_number}
              onClick={() => onVersionSwitch(v.version_number)}
              className={`px-2.5 py-1 text-[10px] rounded whitespace-nowrap transition-colors ${
                v.version_number === currentVersion
                  ? "bg-accent/10 text-accent font-medium"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              title={v.prompt_used}
            >
              v{v.version_number}
            </button>
          ))}
        </div>
        {activeVersion?.diff_download_id && (
          <div className="flex items-center gap-0.5 shrink-0 ml-2">
            <button
              onClick={() => setShowDiff(false)}
              className={`px-2 py-1 text-[10px] rounded ${
                !showDiff
                  ? "bg-accent/10 text-accent"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Edited
            </button>
            <button
              onClick={() => setShowDiff(true)}
              className={`px-2 py-1 text-[10px] rounded ${
                showDiff
                  ? "bg-accent/10 text-accent"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Diff
            </button>
          </div>
        )}
      </div>

      {/* PDF iframe */}
      {loading ? (
        <div className="flex items-center justify-center flex-1">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : pdfUrl ? (
        <iframe
          src={pdfUrl}
          className="flex-1 w-full border-0"
          title="PDF Preview"
        />
      ) : (
        <div className="flex items-center justify-center flex-1 text-xs text-muted-foreground">
          Failed to load PDF
        </div>
      )}
    </div>
  );
}

// ── Download Dropdown ──

function DownloadDropdown({
  versions,
  getVersionPdfUrl,
}: {
  versions: Array<{
    version_number: number;
    download_id: string;
    diff_download_id: string | null;
    prompt_used: string;
  }>;
  getVersionPdfUrl: (downloadId: string) => string;
}) {
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      return () =>
        document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [open]);

  const latest = versions[versions.length - 1];

  async function handleDownload(downloadId: string, filename: string) {
    setOpen(false);
    const url = getVersionPdfUrl(downloadId);
    try {
      let token: string | null = null;
      if (process.env.NEXT_PUBLIC_DEV_MODE !== "true") {
        const supabase = createClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();
        token = session?.access_token ?? null;
      }
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("Download failed");
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    } catch {
      toast.error("Download failed");
    }
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-accent text-accent-foreground rounded-md hover:bg-accent/90 transition-colors"
      >
        <Download className="w-3.5 h-3.5" />
        Download
        <ChevronDown
          className={`w-3 h-3 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-56 rounded-lg border border-border bg-background shadow-lg z-50 py-1">
          {versions
            .slice()
            .reverse()
            .map((v) => (
              <button
                key={v.version_number}
                onClick={() =>
                  handleDownload(
                    v.download_id,
                    `resume-v${v.version_number}.pdf`
                  )
                }
                className="w-full px-3 py-2 text-left hover:bg-muted transition-colors"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium">
                    v{v.version_number}
                  </span>
                  {v.version_number === latest.version_number && (
                    <span className="text-[10px] text-accent">Latest</span>
                  )}
                </div>
                <p className="text-[10px] text-muted-foreground truncate mt-0.5">
                  {v.prompt_used}
                </p>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
