"""action approval requests (v0.1.3.4)

Revision ID: b0a3e6d998fc
Revises: 88c5eab86b3b
Create Date: 2026-09-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b0a3e6d998fc'
down_revision: Union[str, Sequence[str], None] = '88c5eab86b3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'action_approval_requests',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('action_id', sa.String(length=36), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'CANCELLED', name='actionapprovalstatus'),
            nullable=False,
        ),
        sa.Column('requested_by', sa.String(length=320), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('action_summary', sa.Text(), nullable=True),
        sa.Column('risk_summary', sa.Text(), nullable=True),
        sa.Column(
            'permission_level',
            sa.Enum('READ', 'WRITE', 'EXTERNAL_ACTION', 'FINANCIAL_ACTION', 'ADMIN', name='permissionlevel'),
            nullable=False,
        ),
        sa.Column('estimated_cost', sa.Float(), nullable=True),
        sa.Column('proposed_inputs', sa.Text(), nullable=True),
        sa.Column('expected_effect', sa.Text(), nullable=True),
        sa.Column('action_hash', sa.String(length=64), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decided_by', sa.String(length=320), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('consumed', sa.Boolean(), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_action_approval_requests_action_id'),
        'action_approval_requests',
        ['action_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_action_approval_requests_action_id'), table_name='action_approval_requests')
    op.drop_table('action_approval_requests')
