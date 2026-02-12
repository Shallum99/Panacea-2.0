"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useAgenticChat } from "@/hooks/useAgenticChat";
import ConversationSidebar from "@/components/agentic-apply/ConversationSidebar";
import ContextButton from "@/components/agentic-apply/ContextButton";
import ContextModal from "@/components/agentic-apply/ContextModal";
import ChatArea from "@/components/agentic-apply/ChatArea";
import { PanelLeft } from "lucide-react";

function AgenticApplyInner() {
  const searchParams = useSearchParams();
  const state = useAgenticChat(searchParams);
  const [sidebarOpen, setSidebarOpen] = useState(false);

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

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0 relative">
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
                ? state.conversations.find((c) => c.id === state.conversationId)?.title || "Chat"
                : "New chat"}
            </span>
          </div>
          <ContextButton
            context={state.context}
            onClick={() => state.setContextModalOpen(true)}
            showHint={state.messages.length === 0}
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
        />
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
