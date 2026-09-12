"""add oauth_states for single-use OAuth state

Revision ID: a7c4e91f3b52
Revises: d9a6f32bce4c
Create Date: 2026-09-12

Adds the server-side record that makes the OAuth ``state`` parameter genuinely
single-use. Purely additive: no existing table is altered.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a7c4e91f3b52'
down_revision: str | None = 'd9a6f32bce4c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'oauth_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('state_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_oauth_states_state_hash'), 'oauth_states', ['state_hash'], unique=True
    )
    op.create_index(op.f('ix_oauth_states_expires_at'), 'oauth_states', ['expires_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_oauth_states_expires_at'), table_name='oauth_states')
    op.drop_index(op.f('ix_oauth_states_state_hash'), table_name='oauth_states')
    op.drop_table('oauth_states')
