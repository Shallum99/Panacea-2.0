"use client";

import { useState } from "react";
import { Plus, Trash2, MessageSquare } from "lucide-react";

export interface ConversationItem {
  id: number;
  title: string;
  created_at: string | null;
  updated_at: string | null;
}

interface Props {
  conversations: ConversationItem[];
  activeId: number | null;
  onSelect: (id: number) => void;
  onNew: () => void;
  onDelete: (id: number) => void;
  loading?: boolean;
}

function groupByDate(conversations: ConversationItem[]) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);

  const groups: { label: string; items: ConversationItem[] }[] = [
    { label: "Today", items: [] },
    { label: "Yesterday", items: [] },
    { label: "Previous 7 Days", items: [] },
    { label: "Older", items: [] },
  ];

  for (const conv of conversations) {
    const d = new Date(conv.updated_at || conv.created_at || "");
    if (d >= today) groups[0].items.push(conv);
    else if (d >= yesterday) groups[1].items.push(conv);
    else if (d >= weekAgo) groups[2].items.push(conv);
    else groups[3].items.push(conv);
  }

  return groups.filter((g) => g.items.length > 0);
}

function relativeDate(dateStr: string | null): string {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default function ConversationSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  loading,
}: Props) {
  const [hoveredId, setHoveredId] = useState<number | null>(null);
  const groups = groupByDate(conversations);

  return (
    <div className="w-[260px] shrink-0 border-r border-border flex flex-col bg-sidebar h-full">
      {/* New Chat button */}
      <div className="p-3">
        <button
          onClick={onNew}
          className="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl text-[13px] font-medium border border-border hover:border-accent/40 text-foreground transition-all duration-200 hover:bg-foreground/[0.03]"
        >
          <Plus size={15} />
          New Chat
        </button>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {loading ? (
          <div className="space-y-2 px-2 pt-2">
            {[...Array(5)].map((_, i) => (
              <div
                key={i}
                className="h-10 rounded-lg bg-foreground/[0.04] animate-pulse"
              />
            ))}
          </div>
        ) : conversations.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-4 pb-20">
            <MessageSquare
              size={32}
              className="text-muted-foreground/30 mb-3"
            />
            <p className="text-[13px] text-muted-foreground/60">
              Start your first application
            </p>
          </div>
        ) : (
          groups.map((group) => (
            <div key={group.label} className="mt-3 first:mt-0">
              <p className="text-[10px] font-medium text-muted-foreground/50 uppercase tracking-wider px-2 mb-1">
                {group.label}
              </p>
              {group.items.map((conv) => (
                <button
                  key={conv.id}
                  onClick={() => onSelect(conv.id)}
                  onMouseEnter={() => setHoveredId(conv.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  className={`w-full flex items-center justify-between px-2.5 py-2 rounded-lg text-left text-[13px] transition-colors group ${
                    activeId === conv.id
                      ? "bg-foreground/[0.08] text-foreground"
                      : "text-muted-foreground hover:text-foreground hover:bg-foreground/[0.04]"
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate leading-tight">{conv.title}</p>
                    <p className="text-[10px] text-muted-foreground/50 mt-0.5">
                      {relativeDate(conv.updated_at || conv.created_at)}
                    </p>
                  </div>
                  {hoveredId === conv.id && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDelete(conv.id);
                      }}
                      className="shrink-0 ml-1 p-1 rounded-md text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 transition-colors"
                    >
                      <Trash2 size={12} />
                    </button>
                  )}
                </button>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
