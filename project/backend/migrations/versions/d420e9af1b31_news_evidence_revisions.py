"""Preserve source revisions without reusing superseded news features."""
from alembic import op
import sqlalchemy as sa

revision = "d420e9af1b31"
down_revision = "c39fb91a7d20"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("news_facts", sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("news_facts", "superseded_at")
