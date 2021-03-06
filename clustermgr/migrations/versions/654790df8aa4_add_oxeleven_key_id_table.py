"""add oxeleven_key_id table

Revision ID: 654790df8aa4
Revises: dec0f4e419d7
Create Date: 2017-07-21 10:47:44.721562

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '654790df8aa4'
down_revision = 'dec0f4e419d7'
branch_labels = None
depends_on = None


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_table('oxeleven_key_id',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kid', sa.String(length=255), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table("keyrotation") as batch_op:
        batch_op.drop_column('jks_remote_path')
        batch_op.drop_column('oxeleven_kid')
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column(u'keyrotation', sa.Column('oxeleven_kid', sa.VARCHAR(length=255), nullable=True))
    op.add_column(u'keyrotation', sa.Column('jks_remote_path', sa.VARCHAR(length=255), server_default=sa.text(u"'/opt/gluu-server-3.0.1/etc/certs/oxauth-keys.jks'"), nullable=True))
    op.drop_table('oxeleven_key_id')
    ### end Alembic commands ###
