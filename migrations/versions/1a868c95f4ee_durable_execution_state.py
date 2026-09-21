"""durable execution state (v0.1.3.5)

Revision ID: 1a868c95f4ee
Revises: b0a3e6d998fc
Create Date: 2026-09-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a868c95f4ee'
down_revision: Union[str, Sequence[str], None] = 'b0a3e6d998fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ACTION_STATUS_VALUES = (
    'PLANNED', 'VALIDATED', 'PERMISSION_CHECKED', 'WAITING_FOR_APPROVAL', 'APPROVED',
    'EXECUTING', 'EXECUTION_SUCCEEDED', 'VERIFYING', 'VERIFIED', 'VERIFICATION_FAILED',
    'COMPLETED', 'FAILED', 'REJECTED', 'CANCELLED', 'BLOCKED',
)
_ATTEMPT_STATUS_VALUES = (
    'CREATED', 'STARTED', 'SIDE_EFFECT_REPORTED', 'EXECUTION_SUCCEEDED', 'EXECUTION_FAILED',
    'VERIFYING', 'VERIFIED', 'VERIFICATION_FAILED', 'INTERRUPTED', 'RECONCILIATION_REQUIRED',
    'RECONCILED', 'BLOCKED',
)
_PROVENANCE_VALUES = ('ORIGINAL', 'RECONSTRUCTED')
_RISK_LEVEL_VALUES = ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
_PERMISSION_LEVEL_VALUES = ('READ', 'WRITE', 'EXTERNAL_ACTION', 'FINANCIAL_ACTION', 'ADMIN')


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'action_records',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('action_plan_id', sa.String(length=36), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('action_type', sa.String(length=100), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('agent_type', sa.String(length=100), nullable=False),
        sa.Column('tool_name', sa.String(length=200), nullable=True),
        sa.Column('inputs_json', sa.Text(), nullable=True),
        sa.Column('action_hash', sa.String(length=64), nullable=False),
        sa.Column('risk_level', sa.Enum(*_RISK_LEVEL_VALUES, name='risklevel'), nullable=False),
        sa.Column('permission_level', sa.Enum(*_PERMISSION_LEVEL_VALUES, name='permissionlevel'), nullable=False),
        sa.Column('approval_required', sa.Boolean(), nullable=False),
        sa.Column('approval_id', sa.String(length=36), nullable=True),
        sa.Column('estimated_cost', sa.Float(), nullable=True),
        sa.Column('dependencies_json', sa.Text(), nullable=True),
        sa.Column('expected_result', sa.Text(), nullable=True),
        sa.Column('success_criteria', sa.Text(), nullable=True),
        sa.Column('verification_method', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum(*_ACTION_STATUS_VALUES, name='persistedactionstatus'), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('max_retries', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['approval_id'], ['action_approval_requests.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_action_records_action_plan_id'), 'action_records', ['action_plan_id'], unique=False)

    op.create_table(
        'execution_attempts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('action_id', sa.String(length=36), nullable=False),
        sa.Column('idempotency_key', sa.String(length=64), nullable=False),
        sa.Column('tool_name', sa.String(length=200), nullable=False),
        sa.Column('adapter_name', sa.String(length=200), nullable=False),
        sa.Column('adapter_version', sa.String(length=50), nullable=True),
        sa.Column('status', sa.Enum(*_ATTEMPT_STATUS_VALUES, name='executionattemptstatus'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('side_effect_occurred', sa.Boolean(), nullable=False),
        sa.Column('side_effect_fingerprint', sa.String(length=64), nullable=True),
        sa.Column('error_code', sa.String(length=50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('recovery_state', sa.String(length=50), nullable=True),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('claimed_by', sa.String(length=200), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['action_id'], ['action_records.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_execution_attempts_idempotency_key'),
    )
    op.create_index(op.f('ix_execution_attempts_action_id'), 'execution_attempts', ['action_id'], unique=False)

    op.create_table(
        'execution_results',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('attempt_id', sa.String(length=36), nullable=False),
        sa.Column('action_id', sa.String(length=36), nullable=False),
        sa.Column('tool_name', sa.String(length=200), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('provider_status', sa.String(length=100), nullable=True),
        sa.Column('structured_output_json', sa.Text(), nullable=True),
        sa.Column('output_hash', sa.String(length=64), nullable=True),
        sa.Column('side_effect_occurred', sa.Boolean(), nullable=False),
        sa.Column('side_effects_json', sa.Text(), nullable=True),
        sa.Column('cost', sa.Float(), nullable=True),
        sa.Column('error_type', sa.String(length=50), nullable=True),
        sa.Column('error_code', sa.String(length=50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('adapter_version', sa.String(length=50), nullable=True),
        sa.Column('provenance', sa.Enum(*_PROVENANCE_VALUES, name='resultprovenance'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['attempt_id'], ['execution_attempts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('attempt_id', name='uq_execution_results_attempt_id'),
    )
    op.create_index(op.f('ix_execution_results_action_id'), 'execution_results', ['action_id'], unique=False)

    op.create_table(
        'verification_results',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('attempt_id', sa.String(length=36), nullable=False),
        sa.Column('action_id', sa.String(length=36), nullable=False),
        sa.Column('method', sa.String(length=100), nullable=False),
        sa.Column('expected', sa.Text(), nullable=True),
        sa.Column('observed', sa.Text(), nullable=True),
        sa.Column('passed', sa.Boolean(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('issues_json', sa.Text(), nullable=True),
        sa.Column('provenance', sa.Enum(*_PROVENANCE_VALUES, name='resultprovenance'), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['attempt_id'], ['execution_attempts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('attempt_id', name='uq_verification_results_attempt_id'),
    )
    op.create_index(op.f('ix_verification_results_action_id'), 'verification_results', ['action_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_verification_results_action_id'), table_name='verification_results')
    op.drop_table('verification_results')
    op.drop_index(op.f('ix_execution_results_action_id'), table_name='execution_results')
    op.drop_table('execution_results')
    op.drop_index(op.f('ix_execution_attempts_action_id'), table_name='execution_attempts')
    op.drop_table('execution_attempts')
    op.drop_index(op.f('ix_action_records_action_plan_id'), table_name='action_records')
    op.drop_table('action_records')
