"""Local forecasts, immutable news evidence, and forecast pipeline states."""
from alembic import op
import sqlalchemy as sa

revision = "c39fb91a7d20"
down_revision = "b271cd904e12"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("news_facts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("factor", sa.String(32), nullable=False),
        sa.Column("currencies", sa.JSON(), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("claim_type", sa.String(24), nullable=False),
        sa.Column("figures", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("source_title", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("extractor_version", sa.String(32), nullable=False),
        sa.UniqueConstraint("article_id", "evidence_hash", name="uq_news_facts_evidence"))
    op.create_index("ix_news_facts_available", "news_facts", ["available_at"])
    op.create_table("forecast_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_currency", sa.String(3), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_forecast_runs_currency_created", "forecast_runs", ["target_currency", "id"])
    op.drop_constraint("ck_analysis_jobs_state", "analysis_jobs", type_="check")
    op.create_check_constraint("ck_analysis_jobs_state", "analysis_jobs",
        "state IN ('QUEUED','COLLECTING','ANALYZING','EVALUATING_ALERTS','COMPLETED','FAILED','EXTRACTING_HINTS','FORECASTING')")


def downgrade():
    # Retained forecast job histories can contain the new states; preserve validity.
    op.execute("UPDATE analysis_jobs SET state='FAILED', active_key=NULL, attempt_token=NULL, available_at=NULL WHERE state IN ('EXTRACTING_HINTS','FORECASTING')")
    op.drop_constraint("ck_analysis_jobs_state", "analysis_jobs", type_="check")
    op.create_check_constraint("ck_analysis_jobs_state", "analysis_jobs",
        "state IN ('QUEUED','COLLECTING','ANALYZING','EVALUATING_ALERTS','COMPLETED','FAILED')")
    op.drop_index("ix_forecast_runs_currency_created", table_name="forecast_runs")
    op.drop_table("forecast_runs")
    op.drop_index("ix_news_facts_available", table_name="news_facts")
    op.drop_table("news_facts")
