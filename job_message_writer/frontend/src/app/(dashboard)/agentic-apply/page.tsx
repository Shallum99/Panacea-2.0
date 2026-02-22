"use client";

import { Suspense, useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { useAgenticChat } from "@/hooks/useAgenticChat";
import { useArtifactPanel, type Artifact } from "@/hooks/useArtifactPanel";
import ConversationSidebar from "@/components/agentic-apply/ConversationSidebar";
import ContextButton from "@/components/agentic-apply/ContextButton";
import ContextModal from "@/components/agentic-apply/ContextModal";
import ChatArea from "@/components/agentic-apply/ChatArea";
import ArtifactPanel from "@/components/agentic-apply/ArtifactPanel";
import { PanelLeft } from "lucide-react";

const ARTIFACT_TYPES = new Set(["message_preview", "resume_tailored", "resume_score"]);

function extractArtifactTitle(richType: string, data: unknown, versionNum: number): string {
  const d = data as Record<string, unknown>;
  switch (richType) {
    case "message_preview":
      return (d.subject as string) || "Generated Message";
    case "resume_tailored": {
      const name = (d.resume_title as string) || "Resume";
      return `${name} v${versionNum}`;
    }
    case "resume_score":
      return `ATS Score${d.resume_title ? ` \u2014 ${d.resume_title}` : ""}`;
    default:
      return "Artifact";
  }
}

function AgenticApplyInner() {
  const searchParams = useSearchParams();
  const state = useAgenticChat(searchParams);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const artifactPanel = useArtifactPanel();

  // Track previous conversation ID to detect switches
  const prevConvIdRef = useRef<number | null | undefined>(undefined);

  // Clear artifacts when conversation changes
  useEffect(() => {
    if (prevConvIdRef.current !== undefined && prevConvIdRef.current !== state.conversationId) {
      artifactPanel.clearArtifacts();
    }
    prevConvIdRef.current = state.conversationId;
  }, [state.conversationId]);

  // Detect new artifact-worthy messages
  useEffect(() => {
    for (const msg of state.messages) {
      if (
        msg.role === "tool" &&
        msg.richType &&
        ARTIFACT_TYPES.has(msg.richType)
      ) {
        // For resume_tailored, stack versions in the same artifact instead of creating new tabs
        if (msg.richType === "resume_tailored") {
          const existingArtifact = artifactPanel.artifacts.find(
            (a) => a.type === "resume_tailored"
          );
          const existingCount = existingArtifact?.versions?.length ?? 0;
          const versionNum = existingCount + 1;

          const newArtifact: Artifact = {
            id: `artifact-${msg.id}`,
            type: "resume_tailored",
            title: extractArtifactTitle("resume_tailored", msg.richData, versionNum),
            data: msg.richData,
            messageId: msg.id,
            createdAt: Date.now(),
          };

          console.log("[ARTIFACT] resume_tailored msg:", msg.id, "existing:", existingArtifact?.id, "existingVersions:", existingCount);

          // Try stacking onto existing. If no existing, addArtifact creates the first one.
          const stacked = artifactPanel.addVersionToExisting("resume_tailored", newArtifact);
          console.log("[ARTIFACT] addVersionToExisting returned:", stacked);
          if (stacked) continue;

          // First version — create with version info initialized
          const firstTitle = extractArtifactTitle("resume_tailored", msg.richData, 1);
          artifactPanel.addArtifact({
            ...newArtifact,
            title: firstTitle,
            versions: [
              {
                data: msg.richData,
                messageId: msg.id,
                createdAt: Date.now(),
                title: firstTitle,
              },
            ],
            activeVersionIdx: 0,
          });
          console.log("[ARTIFACT] Created first artifact via addArtifact");
          continue;
        }

        // Other artifact types: normal add
        artifactPanel.addArtifact({
          id: `artifact-${msg.id}`,
          type: msg.richType as Artifact["type"],
          title: extractArtifactTitle(msg.richType, msg.richData, 1),
          data: msg.richData,
          messageId: msg.id,
          createdAt: Date.now(),
        });
      }
    }
  }, [state.messages]);

  const handleOpenArtifact = useCallback(
    (messageId: string) => {
      // Check if this messageId is in any artifact's versions
      for (const artifact of artifactPanel.artifacts) {
        if (artifact.messageId === messageId) {
          artifactPanel.openArtifact(artifact.id);
          return;
        }
        if (artifact.versions) {
          const vIdx = artifact.versions.findIndex((v) => v.messageId === messageId);
          if (vIdx !== -1) {
            artifactPanel.setArtifactVersion(artifact.id, vIdx);
            artifactPanel.openArtifact(artifact.id);
            return;
          }
        }
      }
    },
    [artifactPanel.artifacts]
  );

  const activeArtifact =
    artifactPanel.artifacts.find(
      (a) => a.id === artifactPanel.activeArtifactId
    ) || null;

  return (
    <div
      className="flex -m-6 lg:-m-8 bg-black"
      style={{ height: "100vh" }}
    >
      {/* Sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <div
        className={`fixed inset-y-0 left-0 z-50 transform transition-transform duration-200 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <ConversationSidebar
          conversations={state.conversations}
          activeId={state.conversationId}
          onSelect={(id) => {
            state.selectConversation(id);
            setSidebarOpen(false);
          }}
          onNew={() => {
            state.newConversation();
            setSidebarOpen(false);
          }}
          onDelete={state.deleteConversation}
          loading={state.conversationsLoading}
        />
      </div>

      {/* Main area — horizontal split */}
      <div className="flex-1 flex min-w-0">
        {/* Chat column */}
        <div
          className="flex flex-col min-w-0 relative transition-all duration-300 ease-in-out"
          style={{
            flex: artifactPanel.panelOpen ? "1 1 50%" : "1 1 100%",
          }}
        >
          {/* Top bar */}
          <div className="flex items-center justify-between px-4 h-12 shrink-0 border-b border-[#222]">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSidebarOpen(true)}
                className="w-8 h-8 flex items-center justify-center rounded-md text-[#888] hover:text-[#ededed] hover:bg-[#111] transition-colors"
              >
                <PanelLeft size={16} />
              </button>
              <span className="text-[13px] text-[#888]">
                {state.conversationId
                  ? state.conversations.find(
                      (c) => c.id === state.conversationId
                    )?.title || "Chat"
                  : "New chat"}
              </span>
            </div>
            <ContextButton
              context={state.context}
              onClick={() => state.setContextModalOpen(true)}
              showHint={false}
            />
          </div>

          {/* Chat */}
          <ChatArea
            messages={state.messages}
            input={state.input}
            setInput={state.setInput}
            sending={state.sending}
            sendMessage={state.sendMessage}
            context={state.context}
            onScroll={state.handleScroll}
            messagesEndRef={state.messagesEndRef}
            onOpenContext={() => state.setContextModalOpen(true)}
            onOpenArtifact={handleOpenArtifact}
            activeArtifactMessageId={activeArtifact?.messageId || null}
            resumes={state.resumes}
            onSetContext={state.setContext}
            onResumesChanged={state.refreshResumes}
          />
        </div>

        {/* Artifact panel */}
        <div
          className="transition-all duration-300 ease-in-out overflow-hidden"
          style={{
            width: artifactPanel.panelOpen ? "50%" : "0px",
            minWidth: artifactPanel.panelOpen ? "400px" : "0px",
          }}
        >
          {artifactPanel.panelOpen && (
            <ArtifactPanel
              artifact={activeArtifact}
              artifacts={artifactPanel.artifacts}
              onClose={artifactPanel.closePanel}
              onSwitchArtifact={artifactPanel.openArtifact}
              onSendMessage={state.sendMessage}
              onSetVersion={artifactPanel.setArtifactVersion}
            />
          )}
        </div>
      </div>

      {/* Context Modal */}
      <ContextModal
        open={state.contextModalOpen}
        onClose={() => state.setContextModalOpen(false)}
        onSave={state.setContext}
        initialValues={state.context}
        resumes={state.resumes}
      />
    </div>
  );
}

export default function AgenticApplyPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center bg-black text-[#888] text-sm">
          Loading...
        </div>
      }
    >
      <AgenticApplyInner />
    </Suspense>
  );
}
