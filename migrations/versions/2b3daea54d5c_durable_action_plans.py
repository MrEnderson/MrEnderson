"""durable action plans (v0.1.3.6)

Revision ID: 2b3daea54d5c
Revises: 1a868c95f4ee
Create Date: 2026-09-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b3daea54d5c'
down_revision: Union[str, Sequence[str], None] = '1a868c95f4ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'action_plans',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('decision_id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('failure_policy', sa.String(length=50), nullable=False),
        sa.Column('estimated_cost', sa.Float(), nullable=True),
        sa.Column('estimated_model_calls', sa.Integer(), nullable=True),
        sa.Column('success_criteria', sa.Text(), nullable=True),
        sa.Column(
            'status',
            sa.Enum(
                'DRAFT', 'VALIDATING', 'READY', 'WAITING_FOR_APPROVAL', 'EXECUTING',
                'PARTIALLY_COMPLETED', 'COMPLETED', 'FAILED', 'CANCELLED',
                name='persistedactionplanstatus',
            ),
            nullable=False,
        ),
        sa.Column('created_by', sa.String(length=320), nullable=False),
        sa.Column('plan_hash', sa.String(length=64), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('pause_reason', sa.String(length=50), nullable=True),
        sa.Column('reconciliation_required', sa.Boolean(), nullable=False),
        sa.Column('orchestration_owner', sa.String(length=200), nullable=True),
        sa.Column('orchestration_claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('orchestration_lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_action_plans_decision_id'), 'action_plans', ['decision_id'], unique=False)
    op.create_index(op.f('ix_action_plans_status'), 'action_plans', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_action_plans_status'), table_name='action_plans')
    op.drop_index(op.f('ix_action_plans_decision_id'), table_name='action_plans')
    op.drop_table('action_plans')
