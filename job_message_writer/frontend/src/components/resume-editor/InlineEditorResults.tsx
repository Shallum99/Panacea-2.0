"use client";

import { useState } from "react";
import { Check, X, AlertTriangle, Loader2 } from "lucide-react";
import type { DraftEdit } from "@/hooks/useResumeEditor";

// ── Field Edit Result ──

interface FieldEditData {
  field_id: string;
  field_type: string;
  section?: string;
  original_text: string;
  new_text: string;
  reasoning?: string;
  status: string;
  warnings?: string[];
}

export function InlineFieldEdit({ data }: { data: FieldEditData }) {
  return (
    <div className="rounded-lg border border-border bg-background overflow-hidden">
      <div className="px-3 py-2 border-b border-border flex items-center gap-2">
        <span className="text-[10px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
          {data.field_id}
        </span>
        {data.section && (
          <span className="text-[10px] text-muted-foreground">
            {data.section}
          </span>
        )}
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent ml-auto">
          Draft
        </span>
      </div>
      <div className="px-3 py-2 space-y-1.5 text-xs">
        <p className="text-muted-foreground line-through leading-relaxed">
          {data.original_text}
        </p>
        <p className="text-foreground leading-relaxed">{data.new_text}</p>
        {data.reasoning && (
          <p className="text-[10px] text-muted-foreground italic">
            {data.reasoning}
          </p>
        )}
        {data.warnings && data.warnings.length > 0 && (
          <div className="flex items-start gap-1.5 text-[10px] text-yellow-500">
            <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
            <span>{data.warnings.join(". ")}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Edit Suggestions Result ──

interface Suggestion {
  field_id: string;
  field_type: string;
  section?: string;
  original_text: string;
  new_text: string;
  reasoning?: string;
  warnings?: string[];
}

interface EditSuggestionsData {
  instruction: string;
  scope: string;
  total_suggestions: number;
  suggestions: Suggestion[];
}

export function InlineEditSuggestions({
  data,
  onAccept,
}: {
  data: EditSuggestionsData;
  onAccept?: (suggestions: Suggestion[]) => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(
    new Set(data.suggestions.map((s) => s.field_id))
  );

  const toggleSelection = (fieldId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(fieldId)) next.delete(fieldId);
      else next.add(fieldId);
      return next;
    });
  };

  const handleAccept = () => {
    if (onAccept) {
      const accepted = data.suggestions.filter((s) =>
        selected.has(s.field_id)
      );
      onAccept(accepted);
    }
  };

  if (data.suggestions.length === 0) {
    return (
      <div className="px-3 py-2.5 rounded-lg border border-border bg-background text-xs text-muted-foreground">
        No changes suggested for this instruction.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-background overflow-hidden">
      <div className="px-3 py-2 border-b border-border flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          {data.total_suggestions} suggested{" "}
          {data.total_suggestions === 1 ? "change" : "changes"}
        </span>
        {onAccept && (
          <button
            onClick={handleAccept}
            disabled={selected.size === 0}
            className="flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium bg-accent text-accent-foreground rounded hover:bg-accent/90 transition-colors disabled:opacity-50"
          >
            <Check className="w-3 h-3" />
            Apply {selected.size} of {data.total_suggestions}
          </button>
        )}
      </div>
      <div className="divide-y divide-border">
        {data.suggestions.map((s) => (
          <div key={s.field_id} className="px-3 py-2">
            <div className="flex items-start gap-2">
              <button
                onClick={() => toggleSelection(s.field_id)}
                className={`mt-0.5 shrink-0 w-4 h-4 rounded border flex items-center justify-center transition-colors ${
                  selected.has(s.field_id)
                    ? "bg-accent border-accent text-accent-foreground"
                    : "border-border hover:border-muted-foreground"
                }`}
              >
                {selected.has(s.field_id) && <Check className="w-2.5 h-2.5" />}
              </button>
              <div className="flex-1 min-w-0 text-xs">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="text-[10px] font-mono text-muted-foreground bg-muted px-1 py-0.5 rounded">
                    {s.field_id}
                  </span>
                  {s.section && (
                    <span className="text-[10px] text-muted-foreground">
                      {s.section}
                    </span>
                  )}
                </div>
                <p className="text-muted-foreground line-through leading-relaxed">
                  {s.original_text}
                </p>
                <p className="text-foreground leading-relaxed mt-0.5">
                  {s.new_text}
                </p>
                {s.reasoning && (
                  <p className="text-[10px] text-muted-foreground italic mt-0.5">
                    {s.reasoning}
                  </p>
                )}
                {s.warnings && s.warnings.length > 0 && (
                  <div className="flex items-start gap-1 text-[10px] text-yellow-500 mt-0.5">
                    <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                    <span>{s.warnings.join(". ")}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Form Map Preview ──

interface FormMapPreviewData {
  form_map: {
    font_quality: string;
    font_coverage_pct: number;
    total_fields: number;
    editable_fields: number;
    sections: Record<string, number>;
  };
  summary: string;
}

export function InlineFormMapPreview({ data }: { data: FormMapPreviewData }) {
  const fm = data.form_map;
  return (
    <div className="rounded-lg border border-border bg-background overflow-hidden">
      <div className="px-3 py-2 border-b border-border flex items-center gap-2">
        <span className="text-xs font-medium">Resume Fields Loaded</span>
        <span
          className={`text-[10px] px-1.5 py-0.5 rounded ${
            fm.font_quality === "good"
              ? "bg-green-500/10 text-green-500"
              : "bg-yellow-500/10 text-yellow-500"
          }`}
        >
          {fm.font_quality === "good" ? "Good fonts" : "Restricted fonts"}
        </span>
      </div>
      <div className="px-3 py-2 flex flex-wrap gap-2 text-[11px]">
        <span className="px-2 py-0.5 rounded bg-muted text-muted-foreground">
          {fm.editable_fields} editable
        </span>
        <span className="px-2 py-0.5 rounded bg-muted text-muted-foreground">
          {fm.sections.bullets || 0} bullets
        </span>
        <span className="px-2 py-0.5 rounded bg-muted text-muted-foreground">
          {fm.sections.skills || 0} skills
        </span>
        <span className="px-2 py-0.5 rounded bg-muted text-muted-foreground">
          {fm.sections.titles || 0} titles
        </span>
        <span className="px-2 py-0.5 rounded bg-muted text-muted-foreground">
          {fm.font_coverage_pct.toFixed(0)}% font coverage
        </span>
      </div>
    </div>
  );
}

// ── Tool Loading ──

export function InlineToolLoading({
  toolName,
}: {
  toolName: string;
}) {
  const labels: Record<string, string> = {
    get_resume_form_map: "Loading resume fields...",
    edit_resume_field: "Preparing edit...",
    suggest_resume_edits: "Generating suggestions...",
    present_choices: "Preparing options...",
  };
  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-background text-xs text-muted-foreground">
      <Loader2 className="w-3.5 h-3.5 animate-spin" />
      <span>{labels[toolName] || `Using ${toolName}...`}</span>
    </div>
  );
}

// ── Choice Prompt ──

interface Choice {
  label: string;
  description?: string;
}

interface ChoicePromptData {
  prompt: string;
  choices: Choice[];
}

export function InlineChoicePrompt({
  data,
  onChoiceSelected,
}: {
  data: ChoicePromptData;
  onChoiceSelected?: (choice: string) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);

  const handleClick = (label: string) => {
    setSelected(label);
    onChoiceSelected?.(label);
  };

  return (
    <div className="rounded-lg border border-border bg-background overflow-hidden">
      <div className="px-3 py-2.5 text-xs text-foreground">
        {data.prompt}
      </div>
      <div className="px-3 pb-3 flex flex-wrap gap-2">
        {data.choices.map((c) => (
          <button
            key={c.label}
            onClick={() => handleClick(c.label)}
            disabled={selected !== null}
            className={`group relative px-3 py-1.5 text-xs rounded-full border transition-all ${
              selected === c.label
                ? "bg-accent text-accent-foreground border-accent"
                : selected !== null
                  ? "opacity-40 border-border text-muted-foreground cursor-not-allowed"
                  : "border-border text-foreground hover:border-accent hover:text-accent cursor-pointer"
            }`}
          >
            {c.label}
            {c.description && !selected && (
              <span className="hidden group-hover:block absolute left-1/2 -translate-x-1/2 top-full mt-1 px-2 py-1 text-[10px] text-muted-foreground bg-popover border border-border rounded shadow-md whitespace-nowrap z-10">
                {c.description}
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Router ──

export default function EditorInlineResult({
  richType,
  data,
  onAcceptSuggestions,
  onChoiceSelected,
}: {
  richType: string;
  data: unknown;
  onAcceptSuggestions?: (suggestions: Suggestion[]) => void;
  onChoiceSelected?: (choice: string) => void;
}) {
  switch (richType) {
    case "field_edit":
      return <InlineFieldEdit data={data as FieldEditData} />;
    case "edit_suggestions":
      return (
        <InlineEditSuggestions
          data={data as EditSuggestionsData}
          onAccept={onAcceptSuggestions}
        />
      );
    case "choice_prompt":
      return (
        <InlineChoicePrompt
          data={data as ChoicePromptData}
          onChoiceSelected={onChoiceSelected}
        />
      );
    case "form_map":
      return <InlineFormMapPreview data={data as FormMapPreviewData} />;
    case "tool_loading":
      return (
        <InlineToolLoading
          toolName={(data as { tool: string }).tool}
        />
      );
    case "error":
      return (
        <div className="px-3 py-2 rounded-lg border border-red-500/20 bg-red-500/5 text-xs text-red-400">
          {((data as Record<string, unknown>).error as string) ||
            "An error occurred"}
        </div>
      );
    default:
      return null;
  }
}
