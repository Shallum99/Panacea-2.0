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
    <div className="w-[260px] shrink-0 flex flex-col bg-black h-full border-r border-[#1a1a1a]">
      {/* New Chat */}
      <div className="p-3">
        <button
          onClick={onNew}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-[13px] font-medium border border-[#333] text-[#ededed] hover:bg-[#111] transition-colors"
        >
          <Plus size={14} />
          New Chat
        </button>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {loading ? (
          <div className="space-y-2 px-1 pt-2">
            {[...Array(5)].map((_, i) => (
              <div
                key={i}
                className="h-9 rounded-lg bg-[#111] animate-pulse"
              />
            ))}
          </div>
        ) : conversations.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-4 pb-20">
            <MessageSquare size={28} className="text-[#333] mb-3" />
            <p className="text-[12px] text-[#555]">
              No conversations yet
            </p>
          </div>
        ) : (
          groups.map((group) => (
            <div key={group.label} className="mt-4 first:mt-1">
              <p className="text-[10px] font-medium text-[#555] uppercase tracking-wider px-2 mb-1">
                {group.label}
              </p>
              {group.items.map((conv) => (
                <button
                  key={conv.id}
                  onClick={() => onSelect(conv.id)}
                  onMouseEnter={() => setHoveredId(conv.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  className={`w-full flex items-center justify-between px-2.5 py-2 rounded-lg text-left text-[13px] transition-colors ${
                    activeId === conv.id
                      ? "bg-[#1a1a1a] text-[#ededed]"
                      : "text-[#888] hover:text-[#ededed] hover:bg-[#111]"
                  }`}
                >
                  <p className="truncate leading-tight flex-1 min-w-0">
                    {conv.title}
                  </p>
                  {hoveredId === conv.id && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDelete(conv.id);
                      }}
                      className="shrink-0 ml-1 p-1 rounded text-[#555] hover:text-[#ee0000] transition-colors"
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
