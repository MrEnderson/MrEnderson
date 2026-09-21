"""evidence source_quality column (v0.1.3)

Revision ID: f3097cded9d8
Revises: 352f47664add
Create Date: 2026-09-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3097cded9d8'
down_revision: Union[str, Sequence[str], None] = '352f47664add'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'evidence',
        sa.Column('source_quality', sa.String(length=20), nullable=False, server_default='UNKNOWN'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('evidence', 'source_quality')
