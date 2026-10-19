"""Persist forward forecast outcomes without changing issued predictions."""
from alembic import op
import sqlalchemy as sa

revision = "e531f0bc2c42"
down_revision = "d420e9af1b31"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("forecast_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("forecast_run_id", sa.Integer(), sa.ForeignKey("forecast_runs.id"), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("actual_cost", sa.Float(), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(120), nullable=False),
        sa.Column("candidate_errors", sa.JSON(), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("forecast_run_id", name="uq_forecast_outcomes_run"))


def downgrade():
    op.drop_table("forecast_outcomes")
