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

function extractArtifactTitle(richType: string, data: unknown): string {
  const d = data as Record<string, unknown>;
  switch (richType) {
    case "message_preview":
      return (d.subject as string) || "Generated Message";
    case "resume_tailored":
      return `Tailored: ${(d.resume_title as string) || "Resume"}`;
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
        // addArtifact internally dedupes via trackedIdsRef
        artifactPanel.addArtifact({
          id: `artifact-${msg.id}`,
          type: msg.richType as Artifact["type"],
          title: extractArtifactTitle(msg.richType, msg.richData),
          data: msg.richData,
          messageId: msg.id,
          createdAt: Date.now(),
        });
      }
    }
  }, [state.messages]);

  const handleOpenArtifact = useCallback(
    (messageId: string) => {
      const artifact = artifactPanel.artifacts.find(
        (a) => a.messageId === messageId
      );
      if (artifact) {
        artifactPanel.openArtifact(artifact.id);
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
