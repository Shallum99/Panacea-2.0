# File: backend/app/schemas/resume_editor.py
from pydantic import BaseModel
from typing import List, Optional


class FormMapField(BaseModel):
    id: str
    type: str  # "bullet", "skill", "title"
    section: Optional[str] = None
    text: str
    label: Optional[str] = None
    max_chars: Optional[int] = None
    line_count: Optional[int] = None
    char_per_line: Optional[List[int]] = None
    protected: bool = False


class FormMapResponse(BaseModel):
    fields: List[FormMapField]
    editable_fields: int
    font_quality: str
    font_coverage_pct: float
    resume_id: int


class EditRequest(BaseModel):
    prompt: str
    field_targets: Optional[List[str]] = None
    source_version: Optional[int] = None


class EditChange(BaseModel):
    field_id: str
    field_type: str
    section: Optional[str] = None
    original_text: str
    new_text: str
    reasoning: Optional[str] = None
    warnings: Optional[List[str]] = None


class EditResponse(BaseModel):
    version_number: int
    download_id: str
    diff_download_id: Optional[str] = None
    changes: List[EditChange]
    prompt_used: str


class VersionSummary(BaseModel):
    version_number: int
    download_id: str
    diff_download_id: Optional[str] = None
    prompt_used: str
    change_count: int
    created_at: str


class VersionListResponse(BaseModel):
    versions: List[VersionSummary]
    total: int
