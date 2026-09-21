"""evidence evidence_depth column (v0.1.1 checkpoint 3)

Revision ID: 88c5eab86b3b
Revises: f3097cded9d8
Create Date: 2026-09-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '88c5eab86b3b'
down_revision: Union[str, Sequence[str], None] = 'f3097cded9d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'evidence',
        sa.Column('evidence_depth', sa.String(length=20), nullable=False, server_default='SEARCH_SNIPPET'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('evidence', 'evidence_depth')
