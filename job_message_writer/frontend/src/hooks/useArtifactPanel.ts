"use client";

import { useState, useCallback, useRef } from "react";

export interface ArtifactVersion {
  data: unknown;
  messageId: string;
  createdAt: number;
  title: string;
}

export interface Artifact {
  id: string;
  type: "message_preview" | "resume_tailored" | "resume_score";
  title: string;
  data: unknown;
  messageId: string;
  createdAt: number;
  versions?: ArtifactVersion[];
  activeVersionIdx?: number;
}

export function useArtifactPanel() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [activeArtifactId, setActiveArtifactId] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);

  // Track which message IDs already have artifacts (for deduping)
  const trackedIdsRef = useRef(new Set<string>());

  const addArtifact = useCallback(
    (artifact: Artifact, autoOpen = true) => {
      if (trackedIdsRef.current.has(artifact.messageId)) return;
      trackedIdsRef.current.add(artifact.messageId);

      setArtifacts((prev) => [...prev, artifact]);
      if (autoOpen) {
        setActiveArtifactId(artifact.id);
        setPanelOpen(true);
      }
    },
    []
  );

  /** Stack a new version onto an existing artifact of the same type.
   *  Returns true if stacked, false if no existing artifact found. */
  const addVersionToExisting = useCallback(
    (type: Artifact["type"], newArtifact: Artifact): boolean => {
      if (trackedIdsRef.current.has(newArtifact.messageId)) {
        console.log("[VERSION] Already tracked:", newArtifact.messageId);
        return true;
      }

      let found = false;
      setArtifacts((prev) => {
        const existingIdx = prev.findIndex((a) => a.type === type);
        console.log("[VERSION] setArtifacts prev.length:", prev.length, "existingIdx:", existingIdx);
        if (existingIdx === -1) return prev;
        found = true;

        trackedIdsRef.current.add(newArtifact.messageId);

        return prev.map((a, idx) => {
          if (idx !== existingIdx) return a;
          // Build versions array from existing artifact
          const versions: ArtifactVersion[] = a.versions || [
            { data: a.data, messageId: a.messageId, createdAt: a.createdAt, title: a.title },
          ];
          const newVersion: ArtifactVersion = {
            data: newArtifact.data,
            messageId: newArtifact.messageId,
            createdAt: newArtifact.createdAt,
            title: newArtifact.title,
          };
          const updatedVersions = [...versions, newVersion];
          console.log("[VERSION] Stacking version:", updatedVersions.length, "on artifact:", a.id);
          return {
            ...a,
            data: newArtifact.data,
            title: newArtifact.title,
            messageId: newArtifact.messageId,
            versions: updatedVersions,
            activeVersionIdx: updatedVersions.length - 1,
          };
        });
      });

      if (found) {
        // Keep panel open on the same artifact
        setArtifacts((prev) => {
          const existing = prev.find((a) => a.type === type);
          if (existing) setActiveArtifactId(existing.id);
          return prev;
        });
        setPanelOpen(true);
      }

      return found;
    },
    []
  );

  /** Switch version on an artifact that has multiple versions. */
  const setArtifactVersion = useCallback((artifactId: string, versionIdx: number) => {
    setArtifacts((prev) =>
      prev.map((a) => {
        if (a.id !== artifactId || !a.versions || versionIdx >= a.versions.length) return a;
        const v = a.versions[versionIdx];
        return { ...a, data: v.data, title: v.title, activeVersionIdx: versionIdx };
      })
    );
  }, []);

  const openArtifact = useCallback((id: string) => {
    setActiveArtifactId(id);
    setPanelOpen(true);
  }, []);

  const closePanel = useCallback(() => {
    setPanelOpen(false);
  }, []);

  const clearArtifacts = useCallback(() => {
    setArtifacts([]);
    setActiveArtifactId(null);
    setPanelOpen(false);
    trackedIdsRef.current.clear();
  }, []);

  return {
    artifacts,
    activeArtifactId,
    panelOpen,
    addArtifact,
    addVersionToExisting,
    setArtifactVersion,
    openArtifact,
    closePanel,
    clearArtifacts,
  };
}
