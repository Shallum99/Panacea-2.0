# File: backend/app/api/endpoints/resume_editor.py
"""
Resume editor API — form map, prompt-based editing, version history.
Direct prompt → result pipeline (no chat agent).
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Any
import json
import logging
import os
import tempfile
import uuid

from app.db.database import get_db
from app.db import models
from app.schemas.resume_editor import (
    FormMapResponse,
    EditRequest,
    EditResponse,
    EditChange,
    VersionSummary,
    VersionListResponse,
)
from app.services.resume_editor import (
    build_form_map,
    strip_internal_fields,
    apply_prompt_edits,
    generate_diff_pdf,
)
from app.core.supabase_auth import get_current_user
from app.services.storage import (
    is_local_path,
    download_to_tempfile,
    upload_file,
    get_signed_url,
    RESUMES_BUCKET,
    TAILORED_BUCKET,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_resume(db: Session, user: models.User, resume_id: int) -> models.Resume:
    """Get a resume by ID, ensuring ownership."""
    resume = db.query(models.Resume).filter(
        models.Resume.id == resume_id,
        models.Resume.owner_id == user.id,
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    if not resume.file_path:
        raise HTTPException(
            status_code=400,
            detail="Original PDF not found. Re-upload the resume.",
        )
    return resume


@router.get("/{resume_id}/form-map", response_model=FormMapResponse)
async def get_form_map(
    resume_id: int,
    refresh: bool = False,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Parse a resume PDF and return the structured form map of editable fields.
    Caches the result in the resume record; pass refresh=true to rebuild.
    """
    resume = _get_resume(db, current_user, resume_id)

    # Return cached form map if available
    if resume.form_map and not refresh:
        try:
            cached = json.loads(resume.form_map)
            return cached
        except (json.JSONDecodeError, KeyError):
            pass  # rebuild

    # Build form map from PDF
    try:
        if is_local_path(resume.file_path):
            if not os.path.exists(resume.file_path):
                raise HTTPException(status_code=400, detail="PDF file not found on disk.")
            full_map = build_form_map(resume.file_path, resume_id=resume_id)
        else:
            with download_to_tempfile(RESUMES_BUCKET, resume.file_path) as tmp_path:
                full_map = build_form_map(tmp_path, resume_id=resume_id)
    except Exception as e:
        logger.error(f"[EDITOR] Failed to build form map for resume {resume_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to parse resume PDF: {e}")

    # Cache the public form map
    public_map = strip_internal_fields(full_map)
    resume.form_map = json.dumps(public_map)
    resume.font_quality = full_map.get("font_quality", "unknown")
    db.commit()

    return public_map


@router.post("/{resume_id}/edit", response_model=EditResponse)
async def edit_resume(
    resume_id: int,
    request: EditRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Apply a prompt-based edit to a resume PDF.

    1. Determine source PDF (original or a previous version)
    2. Build form map, send prompt to Claude
    3. Apply changes to PDF via content stream engine
    4. Generate diff PDF, upload both to storage
    5. Create ResumeVersion record
    """
    resume = _get_resume(db, current_user, resume_id)

    # Determine source PDF path and version chain
    source_download_id = None
    source_version = None

    if request.source_version is not None:
        # Edit from a specific version
        source_version = db.query(models.ResumeVersion).filter(
            models.ResumeVersion.resume_id == resume_id,
            models.ResumeVersion.version_number == request.source_version,
        ).first()
        if not source_version:
            raise HTTPException(status_code=404, detail=f"Version {request.source_version} not found")
        source_download_id = source_version.download_id

    # Determine next version number
    max_version = db.query(models.ResumeVersion.version_number).filter(
        models.ResumeVersion.resume_id == resume_id,
    ).order_by(models.ResumeVersion.version_number.desc()).first()
    next_version = (max_version[0] + 1) if max_version else 1

    download_id = uuid.uuid4().hex
    diff_download_id = uuid.uuid4().hex

    try:
        if source_download_id:
            # Download the version PDF from Supabase as source
            storage_path = f"{current_user.id}/{source_download_id}.pdf"
            with download_to_tempfile(TAILORED_BUCKET, storage_path) as src_path:
                result = await _run_edit(
                    src_path, resume, request, current_user,
                    download_id, diff_download_id, db,
                )
        elif is_local_path(resume.file_path):
            if not os.path.exists(resume.file_path):
                raise HTTPException(status_code=400, detail="PDF file not found on disk.")
            result = await _run_edit(
                resume.file_path, resume, request, current_user,
                download_id, diff_download_id, db,
            )
        else:
            with download_to_tempfile(RESUMES_BUCKET, resume.file_path) as tmp_path:
                result = await _run_edit(
                    tmp_path, resume, request, current_user,
                    download_id, diff_download_id, db,
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[EDITOR] Edit failed for resume {resume_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Edit failed: {e}")

    # Create version record
    version = models.ResumeVersion(
        resume_id=resume_id,
        version_number=next_version,
        download_id=download_id,
        diff_download_id=diff_download_id,
        parent_version_id=source_version.id if source_version else None,
        prompt_used=request.prompt,
        changes_json=json.dumps(result["changes"]),
        source_download_id=source_download_id,
    )
    db.add(version)
    db.commit()

    # Build response
    changes = [
        EditChange(
            field_id=c["field_id"],
            field_type=c["field_type"],
            section=c.get("section"),
            original_text=c.get("original_text", ""),
            new_text=c.get("new_text", ""),
            reasoning=c.get("reasoning"),
        )
        for c in result["changes"]
    ]

    return EditResponse(
        version_number=next_version,
        download_id=download_id,
        diff_download_id=diff_download_id,
        changes=changes,
        prompt_used=request.prompt,
    )


async def _run_edit(
    pdf_path: str,
    resume: models.Resume,
    request: EditRequest,
    user: models.User,
    download_id: str,
    diff_download_id: str,
    db: Session,
) -> dict:
    """
    Core edit logic: build form map, apply edits, upload results.
    Separated to handle both local and Supabase-sourced PDFs.
    """
    # Build form map (always fresh, not cached — source PDF may be a version)
    form_map = build_form_map(pdf_path, resume_id=resume.id)

    # Create temp output path
    fd, out_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)

    try:
        # Apply prompt edits
        result = await apply_prompt_edits(
            pdf_path=pdf_path,
            output_path=out_path,
            form_map=form_map,
            prompt=request.prompt,
            field_targets=request.field_targets,
        )

        if not result["changes"]:
            logger.info("[EDITOR] No changes were made")
            # Still create the version with no changes
            with open(pdf_path, "rb") as f:
                output_bytes = f.read()
        else:
            with open(out_path, "rb") as f:
                output_bytes = f.read()

        # Upload edited PDF
        tailored_path = f"{user.id}/{download_id}.pdf"
        await upload_file(TAILORED_BUCKET, tailored_path, output_bytes)

        # Generate and upload diff PDF
        try:
            diff_bytes = generate_diff_pdf(pdf_path, output_bytes)
            diff_path = f"{user.id}/{diff_download_id}.pdf"
            await upload_file(TAILORED_BUCKET, diff_path, diff_bytes)
        except Exception as e:
            logger.warning(f"[EDITOR] Failed to generate diff PDF: {e}")

        return result
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


@router.get("/{resume_id}/versions", response_model=VersionListResponse)
async def get_versions(
    resume_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """List all edit versions for a resume."""
    # Verify ownership
    resume = db.query(models.Resume).filter(
        models.Resume.id == resume_id,
        models.Resume.owner_id == current_user.id,
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    versions = db.query(models.ResumeVersion).filter(
        models.ResumeVersion.resume_id == resume_id,
    ).order_by(models.ResumeVersion.version_number.asc()).all()

    summaries = []
    for v in versions:
        change_count = 0
        if v.changes_json:
            try:
                changes = json.loads(v.changes_json)
                change_count = len(changes)
            except (json.JSONDecodeError, TypeError):
                pass

        summaries.append(VersionSummary(
            version_number=v.version_number,
            download_id=v.download_id,
            diff_download_id=v.diff_download_id,
            prompt_used=v.prompt_used,
            change_count=change_count,
            created_at=v.created_at.isoformat() if v.created_at else "",
        ))

    return VersionListResponse(versions=summaries, total=len(summaries))


@router.get("/{resume_id}/download/{download_id}")
async def download_edited_pdf(
    resume_id: int,
    download_id: str,
    current_user: models.User = Depends(get_current_user),
):
    """Download an edited resume PDF via signed URL."""
    storage_path = f"{current_user.id}/{download_id}.pdf"
    try:
        signed_url = get_signed_url(TAILORED_BUCKET, storage_path, expires_in=300)
        return RedirectResponse(url=signed_url)
    except Exception:
        raise HTTPException(status_code=404, detail="PDF not found or expired")
