"use client";

import { useState, useCallback, useRef } from "react";

export interface Artifact {
  id: string;
  type: "message_preview" | "resume_tailored" | "resume_score";
  title: string;
  data: unknown;
  messageId: string;
  createdAt: number;
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
    openArtifact,
    closePanel,
    clearArtifacts,
  };
}
