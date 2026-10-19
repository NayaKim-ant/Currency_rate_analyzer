"""Score each issued horizon independently."""
from alembic import op
import sqlalchemy as sa

revision = "a753b2de4e64"
down_revision = "f642a1cd3d53"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("forecast_outcomes", sa.Column("horizon", sa.Integer(), nullable=False, server_default="1"))
    op.drop_constraint("uq_forecast_outcomes_run", "forecast_outcomes", type_="unique")
    op.create_unique_constraint("uq_forecast_outcomes_run_horizon", "forecast_outcomes", ["forecast_run_id", "horizon"])


def downgrade():
    op.execute("DELETE FROM forecast_outcomes WHERE horizon <> 1")
    op.drop_constraint("uq_forecast_outcomes_run_horizon", "forecast_outcomes", type_="unique")
    op.drop_column("forecast_outcomes", "horizon")
    op.create_unique_constraint("uq_forecast_outcomes_run", "forecast_outcomes", ["forecast_run_id"])
