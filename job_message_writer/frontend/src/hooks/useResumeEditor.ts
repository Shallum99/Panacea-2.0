"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import {
  type FormMapResponse,
  type FormMapField,
  type EditResponse,
  type EditChange,
  type VersionSummary,
  getFormMap,
  editResume,
  getResumeVersions,
  getEditorDownloadUrl,
} from "@/lib/api/resumes";

export interface DraftEdit {
  fieldId: string;
  fieldType: string;
  section?: string;
  originalText: string;
  newText: string;
  reasoning?: string;
  warnings?: string[];
}

export interface EditHistoryItem {
  prompt: string;
  changes: EditChange[];
  versionNumber: number;
  downloadId: string;
  diffDownloadId: string | null;
  timestamp: Date;
}

export function useResumeEditor(resumeId: number) {
  // Form map state
  const [formMap, setFormMap] = useState<FormMapResponse | null>(null);
  const [formMapLoading, setFormMapLoading] = useState(true);
  const [formMapError, setFormMapError] = useState<string | null>(null);

  // Draft state (for manual field edits / quick-edit flow)
  const [drafts, setDrafts] = useState<Record<string, DraftEdit>>({});

  // Edit state
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Edit history (prompt + result pairs)
  const [editHistory, setEditHistory] = useState<EditHistoryItem[]>([]);

  // Version state
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [currentVersion, setCurrentVersion] = useState<number | null>(null);

  // Scroll refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);

  // Auto-scroll when history changes
  useEffect(() => {
    if (autoScrollRef.current && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [editHistory]);

  // Load form map on mount
  useEffect(() => {
    loadFormMap();
    loadVersions();
  }, [resumeId]);

  async function loadFormMap(refresh = false) {
    try {
      setFormMapLoading(true);
      setFormMapError(null);
      const data = await getFormMap(resumeId, refresh);
      setFormMap(data);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load form map";
      setFormMapError(msg);
    } finally {
      setFormMapLoading(false);
    }
  }

  async function loadVersions() {
    try {
      const data = await getResumeVersions(resumeId);
      setVersions(data.versions);
      // Set current version to latest if we have versions
      if (data.versions.length > 0) {
        setCurrentVersion(data.versions[data.versions.length - 1].version_number);
      }
    } catch {
      // Versions are optional — don't block UI
    }
  }

  // ── Draft management ──

  const addDraft = useCallback((edit: DraftEdit) => {
    setDrafts((prev) => ({
      ...prev,
      [edit.fieldId]: edit,
    }));
  }, []);

  const removeDraft = useCallback((fieldId: string) => {
    setDrafts((prev) => {
      const next = { ...prev };
      delete next[fieldId];
      return next;
    });
  }, []);

  const clearDrafts = useCallback(() => {
    setDrafts({});
  }, []);

  const draftCount = Object.keys(drafts).length;

  // ── Submit Edit (core action) ──

  const submitEdit = useCallback(
    async (prompt?: string, fieldTargets?: string[]) => {
      const msg = (prompt || input).trim();
      if (!msg || sending) return null;

      setSending(true);
      setInput("");
      setEditError(null);
      autoScrollRef.current = true;

      try {
        const result = await editResume(
          resumeId,
          msg,
          fieldTargets,
          currentVersion ?? undefined,
        );

        // Add to edit history
        const historyItem: EditHistoryItem = {
          prompt: msg,
          changes: result.changes,
          versionNumber: result.version_number,
          downloadId: result.download_id,
          diffDownloadId: result.diff_download_id,
          timestamp: new Date(),
        };
        setEditHistory((prev) => [...prev, historyItem]);

        // Update current version
        setCurrentVersion(result.version_number);

        // Add new version to versions list
        setVersions((prev) => [
          ...prev,
          {
            version_number: result.version_number,
            download_id: result.download_id,
            diff_download_id: result.diff_download_id,
            prompt_used: msg,
            change_count: result.changes.length,
            created_at: new Date().toISOString(),
          },
        ]);

        // Update form map fields with new text
        if (formMap && result.changes.length > 0) {
          setFormMap((prev) => {
            if (!prev) return prev;
            const updatedFields = prev.fields.map((field) => {
              const change = result.changes.find(
                (c) => c.field_id === field.id
              );
              if (change) {
                return { ...field, text: change.new_text };
              }
              return field;
            });
            return { ...prev, fields: updatedFields };
          });
        }

        // Clear drafts after successful edit
        clearDrafts();

        return result;
      } catch (e) {
        const msg =
          e instanceof Error ? e.message : "Edit failed. Please try again.";
        setEditError(msg);
        return null;
      } finally {
        setSending(false);
      }
    },
    [input, sending, resumeId, currentVersion, formMap, clearDrafts]
  );

  // ── Apply Drafts (manual field edits → batch apply) ──

  const applyDrafts = useCallback(async () => {
    if (draftCount === 0) return null;

    // Build a prompt from drafts
    const draftSummary = Object.values(drafts)
      .map(
        (d) =>
          `Change field "${d.fieldId}" to: "${d.newText}"`
      )
      .join(". ");

    const fieldIds = Object.keys(drafts);
    return submitEdit(
      `Apply these specific changes: ${draftSummary}`,
      fieldIds
    );
  }, [drafts, draftCount, submitEdit]);

  // ── Version navigation ──

  const switchToVersion = useCallback(
    (versionNumber: number | null) => {
      setCurrentVersion(versionNumber);
    },
    []
  );

  // ── URL helpers ──

  const getVersionPdfUrl = useCallback(
    (downloadId: string) => {
      return getEditorDownloadUrl(resumeId, downloadId);
    },
    [resumeId]
  );

  const getCurrentPdfUrl = useCallback(() => {
    if (!currentVersion || versions.length === 0) return null;
    const v = versions.find((v) => v.version_number === currentVersion);
    if (!v) return null;
    return getEditorDownloadUrl(resumeId, v.download_id);
  }, [currentVersion, versions, resumeId]);

  const getCurrentDiffUrl = useCallback(() => {
    if (!currentVersion || versions.length === 0) return null;
    const v = versions.find((v) => v.version_number === currentVersion);
    if (!v?.diff_download_id) return null;
    return getEditorDownloadUrl(resumeId, v.diff_download_id);
  }, [currentVersion, versions, resumeId]);

  // ── Scroll handler ──

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    autoScrollRef.current = isAtBottom;
  }, []);

  return {
    // Form map
    formMap,
    formMapLoading,
    formMapError,
    reloadFormMap: loadFormMap,

    // Drafts
    drafts,
    draftCount,
    addDraft,
    removeDraft,
    clearDrafts,

    // Edit
    input,
    setInput,
    sending,
    editError,
    submitEdit,
    applyDrafts,

    // History
    editHistory,

    // Versions
    versions,
    currentVersion,
    switchToVersion,
    loadVersions,

    // URLs
    getVersionPdfUrl,
    getCurrentPdfUrl,
    getCurrentDiffUrl,

    // Scroll
    messagesEndRef,
    handleScroll,
  };
}
