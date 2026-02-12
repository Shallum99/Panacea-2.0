"use client";

import { useState, useEffect } from "react";
import { X } from "lucide-react";
import type { ChatContext } from "@/lib/api/chat";

interface ResumeOption {
  id: number;
  title: string;
  is_active: boolean;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onSave: (ctx: ChatContext) => void;
  initialValues: ChatContext;
  resumes: ResumeOption[];
}

const MESSAGE_TYPES = [
  { value: "email_detailed", label: "Cover Letter" },
  { value: "email_short", label: "Follow-up" },
  { value: "linkedin_message", label: "Thank You" },
  { value: "linkedin_connection", label: "Referral" },
  { value: "linkedin_inmail", label: "Cold Outreach" },
  { value: "ycombinator", label: "LinkedIn" },
];

export default function ContextModal({
  open,
  onClose,
  onSave,
  initialValues,
  resumes,
}: Props) {
  const [jd, setJd] = useState(initialValues.job_description || "");
  const [resumeId, setResumeId] = useState<number | undefined>(
    initialValues.resume_id
  );
  const [messageType, setMessageType] = useState(
    initialValues.message_type || "email_detailed"
  );
  const [positionTitle, setPositionTitle] = useState(
    initialValues.position_title || ""
  );
  const [recruiterName, setRecruiterName] = useState(
    initialValues.recruiter_name || ""
  );

  useEffect(() => {
    if (open) {
      setJd(initialValues.job_description || "");
      setResumeId(initialValues.resume_id);
      setMessageType(initialValues.message_type || "email_detailed");
      setPositionTitle(initialValues.position_title || "");
      setRecruiterName(initialValues.recruiter_name || "");
    }
  }, [open, initialValues]);

  function handleSave() {
    onSave({
      job_description: jd || undefined,
      resume_id: resumeId,
      message_type: messageType,
      position_title: positionTitle || undefined,
      recruiter_name: recruiterName || undefined,
    });
    onClose();
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg bg-[#0a0a0a] border border-[#222] rounded-xl p-6 mx-4 max-h-[85vh] overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-[15px] font-semibold text-[#ededed]">
            Application Context
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-[#666] hover:text-[#ededed] hover:bg-[#111] transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4">
          {/* Job Description */}
          <div>
            <label className="block text-[12px] font-medium text-[#888] mb-1.5">
              Job Description
            </label>
            <textarea
              value={jd}
              onChange={(e) => setJd(e.target.value)}
              placeholder="Paste the job description..."
              rows={6}
              className="w-full px-3 py-2.5 rounded-lg bg-[#111] border border-[#222] text-[13px] text-[#ededed] placeholder:text-[#444] focus:outline-none focus:border-[#444] resize-none transition-colors"
            />
          </div>

          {/* Resume */}
          <div>
            <label className="block text-[12px] font-medium text-[#888] mb-1.5">
              Resume
            </label>
            <select
              value={resumeId ?? ""}
              onChange={(e) =>
                setResumeId(e.target.value ? Number(e.target.value) : undefined)
              }
              className="w-full px-3 py-2.5 rounded-lg bg-[#111] border border-[#222] text-[13px] text-[#ededed] focus:outline-none focus:border-[#444] transition-colors appearance-none"
            >
              <option value="">Select a resume...</option>
              {resumes.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.title}
                  {r.is_active ? " (Active)" : ""}
                </option>
              ))}
            </select>
          </div>

          {/* Message Type */}
          <div>
            <label className="block text-[12px] font-medium text-[#888] mb-1.5">
              Message Type
            </label>
            <div className="flex flex-wrap gap-1.5">
              {MESSAGE_TYPES.map((mt) => (
                <button
                  key={mt.value}
                  onClick={() => setMessageType(mt.value)}
                  className={`px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors ${
                    messageType === mt.value
                      ? "bg-[#ededed] text-black"
                      : "bg-[#111] text-[#888] border border-[#222] hover:border-[#444] hover:text-[#ededed]"
                  }`}
                >
                  {mt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Position & Recruiter */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[12px] font-medium text-[#888] mb-1.5">
                Position Title
              </label>
              <input
                type="text"
                value={positionTitle}
                onChange={(e) => setPositionTitle(e.target.value)}
                placeholder="e.g. Senior Engineer"
                className="w-full px-3 py-2.5 rounded-lg bg-[#111] border border-[#222] text-[13px] text-[#ededed] placeholder:text-[#444] focus:outline-none focus:border-[#444] transition-colors"
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[#888] mb-1.5">
                Recruiter Name
              </label>
              <input
                type="text"
                value={recruiterName}
                onChange={(e) => setRecruiterName(e.target.value)}
                placeholder="e.g. John Smith"
                className="w-full px-3 py-2.5 rounded-lg bg-[#111] border border-[#222] text-[13px] text-[#ededed] placeholder:text-[#444] focus:outline-none focus:border-[#444] transition-colors"
              />
            </div>
          </div>
        </div>

        {/* Save */}
        <div className="mt-6 flex justify-end">
          <button
            onClick={handleSave}
            className="px-5 py-2 text-[13px] font-medium bg-[#ededed] text-black rounded-lg hover:bg-white transition-colors"
          >
            Save Context
          </button>
        </div>
      </div>
    </div>
  );
}
