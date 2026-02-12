"use client";

import { useState } from "react";
import { Copy, Check, Pencil, RotateCw } from "lucide-react";

interface MessageData {
  message?: string;
  subject?: string;
  message_type?: string;
  application_id?: number;
  resume_used?: string;
}

interface Props {
  data: MessageData;
  onSendMessage?: (text: string) => void;
}

export default function InlineMessagePreview({ data, onSendMessage }: Props) {
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editedBody, setEditedBody] = useState(data.message || "");

  async function handleCopy() {
    await navigator.clipboard.writeText(data.message || "");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="rounded-lg border border-[#222] bg-[#0a0a0a] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#1a1a1a]">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[12px] font-medium text-[#ededed] truncate">
            {data.subject || "Generated Message"}
          </span>
          {data.message_type && (
            <span className="shrink-0 px-2 py-0.5 rounded text-[10px] bg-[#1a1a1a] text-[#888]">
              {data.message_type}
            </span>
          )}
        </div>
        <div className="flex items-center gap-0.5 shrink-0">
          <button
            onClick={handleCopy}
            className="p-1.5 rounded text-[#555] hover:text-[#ededed] transition-colors"
            title="Copy"
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
          </button>
          <button
            onClick={() => setEditing(!editing)}
            className="p-1.5 rounded text-[#555] hover:text-[#ededed] transition-colors"
            title="Edit"
          >
            <Pencil size={12} />
          </button>
          {onSendMessage && data.application_id && (
            <button
              onClick={() =>
                onSendMessage("Make this message shorter and more direct")
              }
              className="p-1.5 rounded text-[#555] hover:text-[#ededed] transition-colors"
              title="Iterate"
            >
              <RotateCw size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        {editing ? (
          <div className="space-y-2">
            <textarea
              value={editedBody}
              onChange={(e) => setEditedBody(e.target.value)}
              className="w-full bg-[#111] border border-[#222] rounded-lg px-3 py-2 text-[12px] text-[#ededed] leading-relaxed resize-none min-h-[120px] outline-none focus:border-[#444]"
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setEditing(false)}
                className="px-3 py-1.5 text-[11px] text-[#888] hover:text-[#ededed] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => setEditing(false)}
                className="px-3 py-1.5 text-[11px] rounded-md bg-[#ededed] text-black"
              >
                Save
              </button>
            </div>
          </div>
        ) : (
          <div className="text-[12px] text-[#999] leading-relaxed whitespace-pre-wrap max-h-[300px] overflow-y-auto">
            {data.message}
          </div>
        )}
      </div>

      {/* Footer */}
      {data.resume_used && (
        <div className="px-4 py-2 border-t border-[#1a1a1a]">
          <p className="text-[10px] text-[#555]">
            Resume: {data.resume_used}
          </p>
        </div>
      )}
    </div>
  );
}
