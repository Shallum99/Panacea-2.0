"use client";

import { useState } from "react";
import { Copy, Check, Pencil, RotateCw, Mail } from "lucide-react";

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
    <div className="border-l-2 border-accent/40 rounded-xl bg-card/60 overflow-hidden ml-10">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/50">
        <div className="flex items-center gap-2 min-w-0">
          <Mail size={13} className="text-accent shrink-0" />
          <span className="text-[12px] font-medium truncate">
            {data.subject || "Generated Message"}
          </span>
          {data.message_type && (
            <span className="shrink-0 px-2 py-0.5 rounded-full bg-accent/10 text-accent text-[10px]">
              {data.message_type}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={handleCopy}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-foreground/[0.05] transition-colors"
            title="Copy"
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
          </button>
          <button
            onClick={() => setEditing(!editing)}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-foreground/[0.05] transition-colors"
            title="Edit"
          >
            <Pencil size={12} />
          </button>
          {onSendMessage && data.application_id && (
            <button
              onClick={() =>
                onSendMessage("Make this message shorter and more direct")
              }
              className="p-1.5 rounded-md text-muted-foreground hover:text-accent hover:bg-accent/10 transition-colors"
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
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-[12px] leading-relaxed resize-none min-h-[120px] outline-none focus:border-accent/40"
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setEditing(false)}
                className="px-3 py-1.5 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => setEditing(false)}
                className="px-3 py-1.5 text-[11px] rounded-lg bg-accent text-accent-foreground"
              >
                Save
              </button>
            </div>
          </div>
        ) : (
          <div className="text-[12px] text-muted-foreground leading-relaxed whitespace-pre-wrap max-h-[300px] overflow-y-auto">
            {data.message}
          </div>
        )}
      </div>

      {/* Footer */}
      {data.resume_used && (
        <div className="px-4 py-2 border-t border-border/50">
          <p className="text-[10px] text-muted-foreground/50">
            Resume: {data.resume_used}
          </p>
        </div>
      )}
    </div>
  );
}
