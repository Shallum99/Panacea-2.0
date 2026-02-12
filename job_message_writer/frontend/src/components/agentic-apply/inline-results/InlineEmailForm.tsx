"use client";

import { Check, Mail, Send } from "lucide-react";

interface EmailData {
  success?: boolean;
  recipient?: string;
  subject?: string;
  error?: string;
}

interface Props {
  data: EmailData;
}

export default function InlineEmailForm({ data }: Props) {
  if (data.error) {
    return (
      <div className="border-l-2 border-destructive/40 rounded-xl bg-destructive/[0.03] px-4 py-3 ml-10">
        <p className="text-[12px] text-destructive">{data.error}</p>
      </div>
    );
  }

  return (
    <div className="border-l-2 border-success/40 rounded-xl bg-success/[0.03] overflow-hidden ml-10">
      <div className="px-4 py-3">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-6 h-6 rounded-full bg-success/10 flex items-center justify-center">
            <Check size={12} className="text-success" />
          </div>
          <span className="text-[13px] font-medium text-success">
            Email Sent
          </span>
        </div>
        <div className="space-y-1 pl-8">
          <div className="flex items-center gap-2 text-[12px]">
            <Mail size={11} className="text-muted-foreground/50" />
            <span className="text-muted-foreground">
              To: {data.recipient}
            </span>
          </div>
          {data.subject && (
            <div className="flex items-center gap-2 text-[12px]">
              <Send size={11} className="text-muted-foreground/50" />
              <span className="text-muted-foreground">
                Subject: {data.subject}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
