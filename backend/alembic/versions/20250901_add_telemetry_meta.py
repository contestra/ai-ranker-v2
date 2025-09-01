"""Add meta JSONB field and grounded_effective to LLMTelemetry

Revision ID: add_telemetry_meta_20250901
Revises: 
Create Date: 2025-09-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_telemetry_meta_20250901'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Add meta JSONB column and grounded_effective to llm_telemetry table"""
    
    # Add grounded_effective column if it doesn't exist
    op.add_column('llm_telemetry', 
        sa.Column('grounded_effective', sa.Boolean(), nullable=True)
    )
    
    # Set default value for existing rows
    op.execute("UPDATE llm_telemetry SET grounded_effective = grounded WHERE grounded_effective IS NULL")
    
    # Make it non-nullable after setting defaults
    op.alter_column('llm_telemetry', 'grounded_effective',
        nullable=False,
        server_default='false'
    )
    
    # Add meta JSONB column for rich telemetry data
    op.add_column('llm_telemetry',
        sa.Column('meta', postgresql.JSONB(), nullable=True)
    )
    
    # Add indexes for efficient querying
    op.create_index(
        'idx_llm_telemetry_meta_response_api',
        'llm_telemetry',
        [sa.text("(meta->>'response_api')")],
        postgresql_using='btree'
    )
    
    op.create_index(
        'idx_llm_telemetry_meta_grounding_mode',
        'llm_telemetry',
        [sa.text("(meta->>'grounding_mode_requested')")],
        postgresql_using='btree'
    )
    
    op.create_index(
        'idx_llm_telemetry_grounded_effective',
        'llm_telemetry',
        ['grounded_effective'],
        postgresql_using='btree'
    )
    
    # Add GIN index for general JSONB queries
    op.create_index(
        'idx_llm_telemetry_meta_gin',
        'llm_telemetry',
        ['meta'],
        postgresql_using='gin'
    )
    
    # Add comment explaining the meta column
    op.execute("""
        COMMENT ON COLUMN llm_telemetry.meta IS 
        'Rich telemetry metadata including ALS provenance, grounding details, citations, feature flags, and runtime configuration'
    """)
    
    op.execute("""
        COMMENT ON COLUMN llm_telemetry.grounded_effective IS 
        'Whether grounding was actually used (may differ from grounded request due to fallbacks or failures)'
    """)


def downgrade():
    """Remove meta column and grounded_effective from llm_telemetry"""
    
    # Drop indexes first
    op.drop_index('idx_llm_telemetry_meta_gin', table_name='llm_telemetry')
    op.drop_index('idx_llm_telemetry_grounded_effective', table_name='llm_telemetry')
    op.drop_index('idx_llm_telemetry_meta_grounding_mode', table_name='llm_telemetry')
    op.drop_index('idx_llm_telemetry_meta_response_api', table_name='llm_telemetry')
    
    # Drop columns
    op.drop_column('llm_telemetry', 'meta')
    op.drop_column('llm_telemetry', 'grounded_effective')