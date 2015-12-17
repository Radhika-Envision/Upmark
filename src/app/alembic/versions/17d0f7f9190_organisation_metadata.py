"""Organisation metadata

Revision ID: 17d0f7f9190
Revises: 4bccb877048
Create Date: 2015-12-16 02:00:18.799879

"""

# revision identifiers, used by Alembic.
revision = '17d0f7f9190'
down_revision = '4bccb877048'
branch_labels = None
depends_on = None


import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Column, Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref, sessionmaker, relationship
from sqlalchemy.schema import MetaData
from sqlalchemy.sql import table, column

from guid import GUID


metadata = MetaData()
Base = declarative_base(metadata=metadata)
Session = sessionmaker()


# Frozen model; required because we need to generate UUIDs using Python module
class Organisation(Base):
    __tablename__ = 'organisation'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    number_of_customers = Column(Integer, nullable=False)
    region = Column(Text, nullable=False)


class OrgMeta(Base):
    __tablename__ = 'org_meta'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    organisation_id = Column(
        GUID, ForeignKey("organisation.id"), nullable=False)
    number_of_customers = Column(Integer)
    organisation = relationship(
        Organisation, backref=backref('meta', uselist=False))


class OrgLocation(Base):
    __tablename__ = 'org_location'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    organisation_id = Column(
        GUID, ForeignKey("organisation.id"), nullable=False)
    region = Column(Text)
    organisation = relationship(Organisation, backref='regions')


def upgrade():
    op.create_table('org_meta',
        sa.Column('id', postgresql.UUID, nullable=False),
        sa.Column('organisation_id', postgresql.UUID, nullable=False),
        sa.Column('ownership', sa.Enum(
            'government run', 'government owned', 'private', 'shareholder',
            native_enum=False)),
        sa.Column('structure', sa.Enum(
            'internal', 'corporation',
            native_enum=False)),
        sa.Column('asset_types', postgresql.ARRAY(Enum(
            'water wholesale', 'water local',
            'wastewater wholesale', 'wastewater local',
            native_enum=False))),
        sa.Column('regulation_level', sa.Enum(
            'extensive', 'partial', 'none',
            native_enum=False)),
        sa.Column('value_water_hs', sa.Float),
        sa.Column('value_water_l', sa.Float),
        sa.Column('value_wastewater_hs', sa.Float),
        sa.Column('value_wastewater_l', sa.Float),
        sa.Column('operating_cost', sa.Float),
        sa.Column('revenue', sa.Float),
        sa.Column('number_fte', sa.Float),
        sa.Column('number_fte_ext', sa.Float),
        sa.Column('population_served', sa.Integer),
        sa.Column('number_of_customers', sa.Integer),
        sa.Column('volume_supplied', sa.Float),
        sa.Column('volume_collected', sa.Float),
        sa.ForeignKeyConstraint(['organisation_id'], ['organisation.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('org_location',
        sa.Column('id', postgresql.UUID, nullable=False),
        sa.Column('organisation_id', postgresql.UUID, nullable=False),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('licence', sa.Text),
        sa.Column('language', sa.Text),
        sa.Column('country', sa.Text),
        sa.Column('region', sa.Text),
        sa.Column('county', sa.Text),
        sa.Column('state', sa.Text),
        sa.Column('postcode', sa.Text),
        sa.Column('city', sa.Text),
        sa.Column('suburb', sa.Text),
        sa.Column('lon', sa.Float),
        sa.Column('lat', sa.Float),
        sa.ForeignKeyConstraint(['organisation_id'], ['organisation.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    session = Session(bind=op.get_bind())
    for org in session.query(Organisation).all():
        org.meta = OrgMeta()
        org.meta.number_of_customers = org.number_of_customers
        if org.region:
            org_location = OrgLocation(organisation=org)
            org_location.description = org.region
            org_location.region = org.region
            org.locations.append(org_location)
    session.flush()

    op.drop_column('organisation', 'region')
    op.drop_column('organisation', 'number_of_customers')


def downgrade():
    op.add_column('organisation', sa.Column('number_of_customers', sa.INTEGER))
    op.add_column('organisation', sa.Column('region', sa.TEXT))

    op.execute("""UPDATE organisation AS o
                  SET region = '',
                      number_of_customers = 0""")
    op.execute("""UPDATE organisation AS o
                  SET region = coalesce(o_r.region, '')
                  FROM org_location AS o_r
                  WHERE o_r.organisation_id = o.id""")
    op.execute("""UPDATE organisation AS o
                  SET number_of_customers = coalesce(o_m.number_of_customers, 0)
                  FROM org_meta AS o_m
                  WHERE o_m.organisation_id = o.id""")
    op.alter_column('organisation', 'region', nullable=False)
    op.alter_column('organisation', 'number_of_customers', nullable=False)

    op.drop_table('org_location')
    op.drop_table('org_meta')
