"""Persistent pipeline jobs and transition history.

Revision ID: b271cd904e12
Revises: 12e7bbf56b2c
"""

from alembic import op
import sqlalchemy as sa

revision = "b271cd904e12"
down_revision = "12e7bbf56b2c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_type", sa.String(24), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("active_key", sa.String(24), nullable=True),
        sa.Column("attempt_token", sa.String(36), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("active_key"),
        sa.CheckConstraint("state IN ('QUEUED','COLLECTING','ANALYZING','EVALUATING_ALERTS','COMPLETED','FAILED')", name="ck_analysis_jobs_state"),
        sa.CheckConstraint("attempts >= 0 AND max_attempts >= 1", name="ck_analysis_jobs_attempts"),
    )
    op.create_index("ix_analysis_jobs_state_available", "analysis_jobs", ["state", "available_at"])
    op.create_table(
        "job_transitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_state", sa.String(24)),
        sa.Column("to_state", sa.String(24), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_job_transitions_job_id", "job_transitions", ["job_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_job_transitions_job_id", table_name="job_transitions")
    op.drop_table("job_transitions")
    op.drop_index("ix_analysis_jobs_state_available", table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
