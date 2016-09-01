"""Moved response type to own table

Revision ID: 151aa56ffd8
Revises: 1ef306add5e
Create Date: 2016-08-22 03:57:41.057928

"""

# revision identifiers, used by Alembic.
revision = '151aa56ffd8'
down_revision = '1ef306add5e'
branch_labels = None
depends_on = None

import copy

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from guid import GUID


Session = sessionmaker()


def upgrade():
    op.create_table('response_type',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('program_id', GUID(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('parts', postgresql.JSON(), nullable=False),
        sa.Column('formula', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id', 'program_id'),
        sa.ForeignKeyConstraint(
            ['program_id'],
            ['program.id']),
        sa.Index(
            'response_type_target_program_id_id_index',
            'program_id', 'id'),
    )
    op.create_table('measure_variable',
        sa.Column('program_id', GUID(), nullable=False),
        sa.Column('target_measure_id', GUID(), nullable=False),
        sa.Column('target_field', sa.Text(), nullable=False),
        sa.Column('source_field', sa.Text(), nullable=False),
        sa.Column('source_measure_id', GUID(), nullable=False),
        sa.PrimaryKeyConstraint(
            'program_id', 'target_measure_id', 'target_field'),
        sa.ForeignKeyConstraint(
            ['target_measure_id', 'program_id'],
            ['measure.id', 'measure.program_id']),
        sa.ForeignKeyConstraint(
            ['source_measure_id', 'program_id'],
            ['measure.id', 'measure.program_id']),
        sa.ForeignKeyConstraint(
            ['program_id'],
            ['program.id']),
        sa.Index(
            'measure_variable_program_id_target_measure_id_index',
            'program_id', 'target_measure_id'),
        sa.Index(
            'measure_variable_program_id_source_measure_id_index',
            'program_id', 'source_measure_id'),
    )
    op.add_column('measure', sa.Column('response_type_id', GUID()))

    # Migrate response types from JSON to new table. Keep track of the IDs so
    # that response types can be tracked through time.
    tracked_rt_ids = {}
    session = Session(bind=op.get_bind())
    for program in session.query(Program).all():
        for old_rt in program.response_types:
            k = (program.tracking_id, old_rt['id'])
            if k not in tracked_rt_ids:
                tracked_rt_ids[k] = uuid.uuid4()
            response_type = ResponseType(
                id=tracked_rt_ids[k], program=program, name=old_rt['name'],
                parts=old_rt['parts'], formula=old_rt.get('formula'))
            session.add(response_type)
            measures = (session.query(Measure)
                .filter(Measure.response_type_ == old_rt['id'])
                .all())
            for measure in measures:
                measure.response_type = response_type
    session.flush()

    op.create_foreign_key('measure_response_type_id_fkey',
        'measure', 'response_type',
        ['response_type_id', 'program_id'],
        ['id', 'program_id'])
    op.alter_column('measure', 'response_type_id', nullable=False)
    op.drop_column('measure', 'response_type')
    op.drop_column('program', 'response_types')


def downgrade():
    op.add_column('program', sa.Column('response_types', postgresql.JSON()))
    op.add_column('measure', sa.Column('response_type', sa.TEXT()))

    session = Session(bind=op.get_bind())
    for response_type in session.query(ResponseType).all():
        response_types = copy.deepcopy(response_type.program.response_types)
        if response_types is None:
            response_types = []
        response_types.append({
            'id': str(response_type.id),
            'name': response_type.name,
            'parts': response_type.parts,
            'formula': response_type.formula,
        })
        response_type.program.response_types = response_types
        for measure in response_type.measures:
            measure.response_type_ = str(response_type.id)
    session.flush()

    op.alter_column('program', 'response_types', nullable=False)
    op.alter_column('measure', 'response_type', nullable=False)

    op.drop_constraint('measure_response_type_id_fkey', 'measure', type_='foreignkey')
    op.drop_column('measure', 'response_type_id')
    op.drop_table('measure_variable')
    op.drop_table('response_type')


# Frozen schema

from datetime import datetime
import logging
import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref, foreign, relationship
from sqlalchemy.schema import ForeignKeyConstraint, Index, MetaData


metadata = MetaData()
Base = declarative_base(metadata=metadata)


class Program(Base):
    __tablename__ = 'program'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    tracking_id = Column(GUID, default=uuid.uuid4, nullable=False)
    response_types = Column(JSON, nullable=False)


class Measure(Base):
    __tablename__ = 'measure'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    program_id = Column(GUID, nullable=False, primary_key=True)
    response_type_id = Column(GUID, nullable=False)
    response_type_ = Column('response_type', Text, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ['program_id'],
            ['program.id']
        ),
        ForeignKeyConstraint(
            ['response_type_id', 'program_id'],
            ['response_type.id', 'response_type.program_id']
        ),
    )

    program = relationship(Program, backref=backref('measures'))


class ResponseType(Base):
    __tablename__ = 'response_type'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    program_id = Column(
        GUID, ForeignKey('program.id'), nullable=False, primary_key=True)

    name = Column(Text, nullable=False)
    parts = Column(JSON, nullable=False)
    formula = Column(Text)

    program = relationship(Program)


Measure.response_type = relationship(
    ResponseType,
    primaryjoin=(foreign(Measure.response_type_id) == ResponseType.id) &
                (ResponseType.program_id == Measure.program_id))


ResponseType.measures = relationship(
    Measure, back_populates='response_type', passive_deletes=True,
    primaryjoin=(foreign(Measure.response_type_id) == ResponseType.id) &
                (ResponseType.program_id == Measure.program_id))
