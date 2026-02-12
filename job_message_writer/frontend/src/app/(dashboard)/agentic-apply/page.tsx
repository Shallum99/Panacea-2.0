"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useAgenticChat } from "@/hooks/useAgenticChat";
import ConversationSidebar from "@/components/agentic-apply/ConversationSidebar";
import ContextButton from "@/components/agentic-apply/ContextButton";
import ContextModal from "@/components/agentic-apply/ContextModal";
import ChatArea from "@/components/agentic-apply/ChatArea";

function AgenticApplyInner() {
  const searchParams = useSearchParams();
  const state = useAgenticChat(searchParams);

  return (
    <div
      className="flex -m-6 lg:-m-8"
      style={{ height: "calc(100vh)" }}
    >
      {/* Conversation Sidebar */}
      <ConversationSidebar
        conversations={state.conversations}
        activeId={state.conversationId}
        onSelect={state.selectConversation}
        onNew={state.newConversation}
        onDelete={state.deleteConversation}
        loading={state.conversationsLoading}
      />

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        {/* Context button (top-right) */}
        <div className="absolute top-4 right-4 z-10">
          <ContextButton
            context={state.context}
            onClick={() => state.setContextModalOpen(true)}
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
        <div className="flex h-screen items-center justify-center text-muted-foreground text-sm">
          Loading...
        </div>
      }
    >
      <AgenticApplyInner />
    </Suspense>
  );
}
