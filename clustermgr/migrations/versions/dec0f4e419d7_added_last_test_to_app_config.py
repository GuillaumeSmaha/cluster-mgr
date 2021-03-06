"""added last test to app config

Revision ID: dec0f4e419d7
Revises: a1217610461f
Create Date: 2017-07-18 08:50:37.330069

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dec0f4e419d7'
down_revision = 'a1217610461f'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('appconfig', sa.Column('last_test', sa.Boolean(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("appconfig") as batch_op:
        batch_op.drop_column('last_test')
    # ### end Alembic commands ###
