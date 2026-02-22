"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Pencil, X, Shield } from "lucide-react";
import type { FormMapResponse, FormMapField } from "@/lib/api/resumes";
import type { DraftEdit } from "@/hooks/useResumeEditor";

interface Props {
  formMap: FormMapResponse;
  drafts: Record<string, DraftEdit>;
  onRemoveDraft: (fieldId: string) => void;
}

export default function FieldMapView({ formMap, drafts, onRemoveDraft }: Props) {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(["bullets", "skills", "titles"])
  );

  const toggleSection = (key: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  // Group fields by type
  const bullets = formMap.fields.filter((f) => f.type === "bullet");
  const skills = formMap.fields.filter((f) => f.type === "skill");
  const titles = formMap.fields.filter((f) => f.type === "title");

  // Group bullets by section
  const bulletsBySection = bullets.reduce<Record<string, FormMapField[]>>(
    (acc, f) => {
      const section = f.section || "Other";
      if (!acc[section]) acc[section] = [];
      acc[section].push(f);
      return acc;
    },
    {}
  );

  return (
    <div className="h-full overflow-y-auto">
      {/* Header stats */}
      <div className="px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>{formMap.editable_fields} editable fields</span>
          <span className="text-border">|</span>
          <span
            className={
              formMap.font_quality === "good"
                ? "text-green-500"
                : "text-yellow-500"
            }
          >
            {formMap.font_quality === "good" ? "Good fonts" : "Restricted fonts"}
          </span>
          <span className="text-border">|</span>
          <span>{formMap.font_coverage_pct.toFixed(0)}% coverage</span>
        </div>
      </div>

      {/* Bullets section */}
      {Object.entries(bulletsBySection).map(([section, sectionBullets]) => (
        <SectionGroup
          key={section}
          title={section}
          count={sectionBullets.length}
          expanded={expandedSections.has("bullets")}
          onToggle={() => toggleSection("bullets")}
        >
          {sectionBullets.map((field) => (
            <FieldRow
              key={field.id}
              field={field}
              draft={drafts[field.id]}
              onRemoveDraft={onRemoveDraft}
            />
          ))}
        </SectionGroup>
      ))}

      {/* Skills section */}
      {skills.length > 0 && (
        <SectionGroup
          title="Skills"
          count={skills.length}
          expanded={expandedSections.has("skills")}
          onToggle={() => toggleSection("skills")}
        >
          {skills.map((field) => (
            <FieldRow
              key={field.id}
              field={field}
              draft={drafts[field.id]}
              onRemoveDraft={onRemoveDraft}
            />
          ))}
        </SectionGroup>
      )}

      {/* Titles section */}
      {titles.length > 0 && (
        <SectionGroup
          title="Titles"
          count={titles.length}
          expanded={expandedSections.has("titles")}
          onToggle={() => toggleSection("titles")}
        >
          {titles.map((field) => (
            <FieldRow
              key={field.id}
              field={field}
              draft={drafts[field.id]}
              onRemoveDraft={onRemoveDraft}
            />
          ))}
        </SectionGroup>
      )}
    </div>
  );
}

function SectionGroup({
  title,
  count,
  expanded,
  onToggle,
  children,
}: {
  title: string;
  count: number;
  expanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="border-b border-border">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-muted/50 transition-colors text-left"
      >
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
        )}
        <span className="text-xs font-medium">{title}</span>
        <span className="text-[10px] text-muted-foreground ml-auto">
          {count}
        </span>
      </button>
      {expanded && <div className="pb-2">{children}</div>}
    </div>
  );
}

function FieldRow({
  field,
  draft,
  onRemoveDraft,
}: {
  field: FormMapField;
  draft?: DraftEdit;
  onRemoveDraft: (fieldId: string) => void;
}) {
  const hasDraft = !!draft;

  return (
    <div
      className={`mx-3 mb-1.5 rounded-lg border px-3 py-2 text-xs transition-colors ${
        hasDraft
          ? "border-accent/30 bg-accent/5"
          : "border-border bg-background"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {/* Field ID badge */}
          <div className="flex items-center gap-1.5 mb-1">
            <span className="text-[10px] font-mono text-muted-foreground bg-muted px-1 py-0.5 rounded">
              {field.id}
            </span>
            {field.protected && (
              <Shield className="w-3 h-3 text-muted-foreground" />
            )}
            {field.max_chars && (
              <span className="text-[10px] text-muted-foreground">
                max {field.max_chars}
              </span>
            )}
          </div>

          {/* Original text */}
          {hasDraft ? (
            <>
              <p className="text-muted-foreground line-through leading-relaxed">
                {draft.originalText}
              </p>
              <p className="text-accent leading-relaxed mt-0.5">
                {draft.newText}
              </p>
              {draft.warnings && draft.warnings.length > 0 && (
                <div className="mt-1">
                  {draft.warnings.map((w, i) => (
                    <p key={i} className="text-[10px] text-yellow-500">
                      {w}
                    </p>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="text-foreground leading-relaxed">{field.text}</p>
          )}

          {/* Label for skills */}
          {field.label && (
            <p className="text-[10px] text-muted-foreground mt-0.5">
              Label: {field.label}
            </p>
          )}
        </div>

        {/* Actions */}
        {hasDraft && (
          <button
            onClick={() => onRemoveDraft(field.id)}
            className="shrink-0 p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            title="Remove change"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}
