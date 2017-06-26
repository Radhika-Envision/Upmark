"""Added response_types to Survey

Revision ID: 145f93a3f88
Revises: 1ba14f036a
Create Date: 2015-08-09 13:40:58.399662

"""

# revision identifiers, used by Alembic.
revision = '145f93a3f88'
down_revision = '1ba14f036a'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import MetaData

from old_deps.guid import GUID


metadata = MetaData()
Base = declarative_base(metadata=metadata)
Session = sessionmaker()


class Survey(Base):
    # Frozen schema (some columns omitted)
    __tablename__ = 'survey'
    id = sa.Column(GUID, primary_key=True)
    response_types = sa.Column(postgresql.JSON)


def upgrade():
    session = Session(bind=op.get_bind())
    op.add_column('survey', sa.Column(
        'response_types', postgresql.JSON(), nullable=True))

    surveys = session.query(Survey).all()
    for survey in surveys:
        survey.response_types = []
    session.flush()

    op.alter_column('survey', 'response_types', nullable=False)


def downgrade():
    op.drop_column('survey', 'response_types')
