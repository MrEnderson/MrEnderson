"""failure intelligence, bounded retry, replan, budgets (v0.1.3.7)

Revision ID: 7f2c9a1e4b6d
Revises: 2b3daea54d5c
Create Date: 2026-09-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f2c9a1e4b6d'
down_revision: Union[str, Sequence[str], None] = '2b3daea54d5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('action_records', sa.Column('superseded_by_action_id', sa.String(length=36), nullable=True))
    op.add_column('action_plans', sa.Column('revision', sa.Integer(), nullable=False, server_default='1'))

    op.create_table(
        'failure_records',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('action_id', sa.String(length=36), nullable=False),
        sa.Column('plan_id', sa.String(length=36), nullable=False),
        sa.Column('execution_attempt_id', sa.String(length=36), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('side_effect_occurred', sa.Boolean(), nullable=False),
        sa.Column('retry_safe', sa.Boolean(), nullable=False),
        sa.Column('reconciliation_required', sa.Boolean(), nullable=False),
        sa.Column('retry_count_at_failure', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_failure_records_action_id'), 'failure_records', ['action_id'], unique=False)
    op.create_index(op.f('ix_failure_records_plan_id'), 'failure_records', ['plan_id'], unique=False)

    op.create_table(
        'recovery_decisions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('failure_id', sa.String(length=36), nullable=False),
        sa.Column('action_id', sa.String(length=36), nullable=False),
        sa.Column('plan_id', sa.String(length=36), nullable=False),
        sa.Column('decision', sa.String(length=50), nullable=False),
        sa.Column('reason_codes_json', sa.Text(), nullable=True),
        sa.Column('retry_number', sa.Integer(), nullable=True),
        sa.Column('replan_proposal_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_recovery_decisions_action_id'), 'recovery_decisions', ['action_id'], unique=False)
    op.create_index(op.f('ix_recovery_decisions_plan_id'), 'recovery_decisions', ['plan_id'], unique=False)

    op.create_table(
        'replan_proposals',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('plan_id', sa.String(length=36), nullable=False),
        sa.Column('failed_action_id', sa.String(length=36), nullable=False),
        sa.Column('replacement_action_id', sa.String(length=36), nullable=False),
        sa.Column('replacement_action_type', sa.String(length=100), nullable=False),
        sa.Column('replacement_title', sa.String(length=500), nullable=False),
        sa.Column('replacement_tool_name', sa.String(length=200), nullable=True),
        sa.Column('replacement_inputs_json', sa.Text(), nullable=True),
        sa.Column('replacement_expected_result', sa.Text(), nullable=True),
        sa.Column('replacement_success_criteria', sa.Text(), nullable=True),
        sa.Column('replacement_verification_method', sa.Text(), nullable=True),
        sa.Column(
            'replacement_permission_level',
            sa.Enum('READ', 'WRITE', 'EXTERNAL_ACTION', 'FINANCIAL_ACTION', 'ADMIN', name='permissionlevel'),
            nullable=False,
        ),
        sa.Column(
            'replacement_risk_level',
            sa.Enum('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='risklevel'),
            nullable=False,
        ),
        sa.Column('replacement_dependencies_json', sa.Text(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('failure_category', sa.String(length=50), nullable=True),
        sa.Column(
            'status',
            sa.Enum('PROPOSED', 'APPLIED', 'REJECTED', 'CANCELLED', name='replanproposalstatus'),
            nullable=False,
        ),
        sa.Column('reason_codes_json', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=320), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('new_plan_revision', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_replan_proposals_plan_id'), 'replan_proposals', ['plan_id'], unique=False)
    op.create_index(op.f('ix_replan_proposals_failed_action_id'), 'replan_proposals', ['failed_action_id'], unique=False)

    op.create_table(
        'budget_accounts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('scope_type', sa.Enum('ACTION', 'PLAN', name='budgetscope'), nullable=False),
        sa.Column('scope_id', sa.String(length=36), nullable=False),
        sa.Column(
            'budget_type',
            sa.Enum('ACTION_ATTEMPTS', 'RETRIES', 'REPLANS', 'MODEL_CALLS', 'ESTIMATED_COST', name='budgettype'),
            nullable=False,
        ),
        sa.Column('limit_value', sa.Float(), nullable=False),
        sa.Column('consumed_value', sa.Float(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('ACTIVE', 'EXHAUSTED', 'CANCELLED', name='budgetaccountstatus'),
            nullable=False,
        ),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scope_type', 'scope_id', 'budget_type', name='uq_budget_account_scope_type'),
    )

    op.create_table(
        'budget_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('budget_account_id', sa.String(length=36), nullable=False),
        sa.Column('idempotency_key', sa.String(length=200), nullable=False),
        sa.Column('delta', sa.Float(), nullable=False),
        sa.Column('applied', sa.Boolean(), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['budget_account_id'], ['budget_accounts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_budget_events_idempotency_key'),
    )
    op.create_index(op.f('ix_budget_events_account_id'), 'budget_events', ['budget_account_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_budget_events_account_id'), table_name='budget_events')
    op.drop_table('budget_events')
    op.drop_table('budget_accounts')
    op.drop_index(op.f('ix_replan_proposals_failed_action_id'), table_name='replan_proposals')
    op.drop_index(op.f('ix_replan_proposals_plan_id'), table_name='replan_proposals')
    op.drop_table('replan_proposals')
    op.drop_index(op.f('ix_recovery_decisions_plan_id'), table_name='recovery_decisions')
    op.drop_index(op.f('ix_recovery_decisions_action_id'), table_name='recovery_decisions')
    op.drop_table('recovery_decisions')
    op.drop_index(op.f('ix_failure_records_plan_id'), table_name='failure_records')
    op.drop_index(op.f('ix_failure_records_action_id'), table_name='failure_records')
    op.drop_table('failure_records')
    op.drop_column('action_plans', 'revision')
    op.drop_column('action_records', 'superseded_by_action_id')
