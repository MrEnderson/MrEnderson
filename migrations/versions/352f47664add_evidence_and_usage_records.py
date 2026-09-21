"""evidence and usage records (v0.1.1)

Revision ID: 352f47664add
Revises: 2974c89766cf
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '352f47664add'
down_revision: Union[str, Sequence[str], None] = '2974c89766cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('evidence',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('workspace_id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('task_id', sa.String(length=36), nullable=False),
    sa.Column('claim', sa.Text(), nullable=False),
    sa.Column('source_title', sa.String(length=500), nullable=True),
    sa.Column('source_url', sa.String(length=2000), nullable=True),
    sa.Column('publisher', sa.String(length=255), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('excerpt', sa.Text(), nullable=True),
    sa.Column('evidence_type', sa.Enum('PRIMARY_SOURCE', 'NEWS', 'OFFICIAL_STATISTIC', 'ACADEMIC', 'COMPANY_DISCLOSURE', 'BLOG_OR_OPINION', 'OTHER', name='evidencekind'), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('query_used', sa.String(length=500), nullable=True),
    sa.Column('verification_status', sa.Enum('RETRIEVED', 'VERIFIED', 'UNVERIFIED', 'MOCK', name='evidenceverificationstatus'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_evidence_workspace_id'), 'evidence', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_evidence_project_id'), 'evidence', ['project_id'], unique=False)
    op.create_index(op.f('ix_evidence_task_id'), 'evidence', ['task_id'], unique=False)
    op.create_index('ix_evidence_project_task', 'evidence', ['project_id', 'task_id'], unique=False)

    op.create_table('usage_records',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('workspace_id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('task_id', sa.String(length=36), nullable=True),
    sa.Column('agent_type', sa.String(length=100), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('model', sa.String(length=100), nullable=False),
    sa.Column('input_tokens', sa.Integer(), nullable=True),
    sa.Column('output_tokens', sa.Integer(), nullable=True),
    sa.Column('total_tokens', sa.Integer(), nullable=True),
    sa.Column('api_calls', sa.Integer(), nullable=False),
    sa.Column('retry_number', sa.Integer(), nullable=False),
    sa.Column('elapsed_ms', sa.Float(), nullable=True),
    sa.Column('estimated_cost_usd', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_usage_records_workspace_id'), 'usage_records', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_usage_records_project_id'), 'usage_records', ['project_id'], unique=False)
    op.create_index(op.f('ix_usage_records_task_id'), 'usage_records', ['task_id'], unique=False)
    op.create_index('ix_usage_workspace_created', 'usage_records', ['workspace_id', 'created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_usage_workspace_created', table_name='usage_records')
    op.drop_index(op.f('ix_usage_records_task_id'), table_name='usage_records')
    op.drop_index(op.f('ix_usage_records_project_id'), table_name='usage_records')
    op.drop_index(op.f('ix_usage_records_workspace_id'), table_name='usage_records')
    op.drop_table('usage_records')

    op.drop_index('ix_evidence_project_task', table_name='evidence')
    op.drop_index(op.f('ix_evidence_task_id'), table_name='evidence')
    op.drop_index(op.f('ix_evidence_project_id'), table_name='evidence')
    op.drop_index(op.f('ix_evidence_workspace_id'), table_name='evidence')
    op.drop_table('evidence')
