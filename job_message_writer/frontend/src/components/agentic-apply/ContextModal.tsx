"use client";

import { useState, useEffect } from "react";
import { X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
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

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.2 }}
            className="relative w-full max-w-lg bg-card border border-border rounded-2xl shadow-2xl p-6 mx-4 max-h-[85vh] overflow-y-auto"
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-base font-semibold">Application Context</h2>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-foreground/[0.05] transition-colors"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-4">
              {/* Job Description */}
              <div>
                <label className="block text-[12px] font-medium text-muted-foreground mb-1.5">
                  Job Description
                </label>
                <textarea
                  value={jd}
                  onChange={(e) => setJd(e.target.value)}
                  placeholder="Paste the job description..."
                  rows={6}
                  className="w-full px-3 py-2.5 rounded-xl bg-background border border-border text-[13px] placeholder:text-muted-foreground/40 focus:outline-none focus:border-accent/40 resize-none transition-colors"
                />
              </div>

              {/* Resume */}
              <div>
                <label className="block text-[12px] font-medium text-muted-foreground mb-1.5">
                  Resume
                </label>
                <select
                  value={resumeId ?? ""}
                  onChange={(e) =>
                    setResumeId(e.target.value ? Number(e.target.value) : undefined)
                  }
                  className="w-full px-3 py-2.5 rounded-xl bg-background border border-border text-[13px] focus:outline-none focus:border-accent/40 transition-colors appearance-none"
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
                <label className="block text-[12px] font-medium text-muted-foreground mb-1.5">
                  Message Type
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {MESSAGE_TYPES.map((mt) => (
                    <button
                      key={mt.value}
                      onClick={() => setMessageType(mt.value)}
                      className={`px-3 py-1.5 rounded-full text-[12px] font-medium transition-all duration-150 ${
                        messageType === mt.value
                          ? "bg-accent/15 text-accent border border-accent/30"
                          : "bg-foreground/[0.03] text-muted-foreground border border-transparent hover:border-border hover:text-foreground"
                      }`}
                    >
                      {mt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Position & Recruiter (side by side) */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[12px] font-medium text-muted-foreground mb-1.5">
                    Position Title
                  </label>
                  <input
                    type="text"
                    value={positionTitle}
                    onChange={(e) => setPositionTitle(e.target.value)}
                    placeholder="e.g. Senior Engineer"
                    className="w-full px-3 py-2.5 rounded-xl bg-background border border-border text-[13px] placeholder:text-muted-foreground/40 focus:outline-none focus:border-accent/40 transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-[12px] font-medium text-muted-foreground mb-1.5">
                    Recruiter Name
                  </label>
                  <input
                    type="text"
                    value={recruiterName}
                    onChange={(e) => setRecruiterName(e.target.value)}
                    placeholder="e.g. John Smith"
                    className="w-full px-3 py-2.5 rounded-xl bg-background border border-border text-[13px] placeholder:text-muted-foreground/40 focus:outline-none focus:border-accent/40 transition-colors"
                  />
                </div>
              </div>
            </div>

            {/* Save button */}
            <div className="mt-6 flex justify-end">
              <button onClick={handleSave} className="btn-gradient px-5 py-2.5 text-[13px]">
                Save Context
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
