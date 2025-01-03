"""add title and convert_to_mp3 fields

Revision ID: 06ae11c2691f
Revises: 
Create Date: 2024-12-31 20:57:37.889856

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '06ae11c2691f'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('downloads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('title', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('convert_to_mp3', sa.Boolean(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('downloads', schema=None) as batch_op:
        batch_op.drop_column('convert_to_mp3')
        batch_op.drop_column('title')

    # ### end Alembic commands ###
