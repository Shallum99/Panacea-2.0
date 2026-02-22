"""add resume editor tables

Revision ID: a1b2c3d4e5f6
Revises: 735816ae3c23
Create Date: 2026-02-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '735816ae3c23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add cached form map columns to resumes
    op.add_column('resumes', sa.Column('form_map', sa.Text(), nullable=True))
    op.add_column('resumes', sa.Column('font_quality', sa.String(), nullable=True))

    # Create resume_versions table
    op.create_table(
        'resume_versions',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('resume_id', sa.Integer(), sa.ForeignKey('resumes.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('download_id', sa.String(), nullable=False),
        sa.Column('diff_download_id', sa.String(), nullable=True),
        sa.Column('parent_version_id', sa.Integer(), sa.ForeignKey('resume_versions.id'), nullable=True),
        sa.Column('prompt_used', sa.Text(), nullable=False),
        sa.Column('changes_json', sa.Text(), nullable=True),
        sa.Column('source_download_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('resume_versions')
    op.drop_column('resumes', 'font_quality')
    op.drop_column('resumes', 'form_map')
