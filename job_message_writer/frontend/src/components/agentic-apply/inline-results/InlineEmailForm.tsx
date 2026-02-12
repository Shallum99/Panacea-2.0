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
      <div className="rounded-lg border border-[#222] bg-[#0a0a0a] px-4 py-3">
        <p className="text-[12px] text-[#ee0000]">{data.error}</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-[#222] bg-[#0a0a0a] overflow-hidden">
      <div className="px-4 py-3">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-5 h-5 rounded-full bg-[#1a1a1a] flex items-center justify-center">
            <Check size={11} className="text-[#50e3c2]" />
          </div>
          <span className="text-[13px] font-medium text-[#ededed]">
            Email Sent
          </span>
        </div>
        <div className="space-y-1 pl-7">
          <div className="flex items-center gap-2 text-[12px]">
            <Mail size={11} className="text-[#555]" />
            <span className="text-[#888]">To: {data.recipient}</span>
          </div>
          {data.subject && (
            <div className="flex items-center gap-2 text-[12px]">
              <Send size={11} className="text-[#555]" />
              <span className="text-[#888]">Subject: {data.subject}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
