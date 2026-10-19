"""Keep structured event fields with their immutable evidence vintage."""
from alembic import op
import sqlalchemy as sa

revision = "f642a1cd3d53"
down_revision = "e531f0bc2c42"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("news_facts", sa.Column("event", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("news_facts", "event")
