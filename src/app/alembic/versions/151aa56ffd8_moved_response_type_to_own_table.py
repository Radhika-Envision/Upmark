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


response = sa.sql.table('response',
    sa.sql.column('variables', postgresql.JSON)
)


def upgrade():
    upgrade_qnode_measure()
    upgrade_response()
    upgrade_rnode()
    upgrade_response_type()
    upgrade_activity()
    upgrade_variable()
    upgrade_errors()


def upgrade_variable():
    op.create_table('measure_variable',
        sa.Column('program_id', GUID(), nullable=False),
        sa.Column('survey_id', GUID(), nullable=False),
        sa.Column('target_measure_id', GUID(), nullable=False),
        sa.Column('target_field', sa.Text(), nullable=False),
        sa.Column('source_measure_id', GUID(), nullable=False),
        sa.Column('source_field', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            'program_id', 'survey_id', 'target_measure_id', 'target_field'),
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
    op.add_column('response', sa.Column('variables', postgresql.JSON()))
    op.execute(response.update().values({'variables': {}}))
    op.alter_column('response', 'variables', nullable=False)


def upgrade_qnode_measure():
    # Change primary key of qnode_measure
    op.rename_table('qnode_measure_link', 'qnode_measure')
    op.execute("""ALTER TABLE qnode_measure
        RENAME CONSTRAINT qnode_measure_link_pkey
        TO qnode_measure_pkey""")
    op.execute("""ALTER TABLE qnode_measure
        RENAME CONSTRAINT qnode_measure_link_measure_id_fkey
        TO qnode_measure_measure_id_fkey""")
    op.execute("""ALTER TABLE qnode_measure
        RENAME CONSTRAINT qnode_measure_link_program_id_fkey
        TO qnode_measure_program_id_fkey;""")
    op.execute("""ALTER TABLE qnode_measure
        RENAME CONSTRAINT qnode_measure_link_qnode_id_fkey
        TO qnode_measure_qnode_id_fkey;""")
    op.execute("""ALTER INDEX IF EXISTS qnodemeasure_measure_id_survey_id_index
        RENAME TO qnodemeasure_measure_id_program_id_index""")
    op.execute("""ALTER INDEX IF EXISTS qnodemeasure_qnode_id_survey_id_index
        RENAME TO qnodemeasure_qnode_id_program_id_index""")
    op.add_column('qnode_measure', sa.Column('survey_id', GUID()))
    op.execute("""
        UPDATE qnode_measure AS qm
        SET survey_id = q.survey_id
        FROM qnode AS q
        WHERE q.program_id = qm.program_id
            AND q.id = qm.qnode_id
        """)
    op.alter_column('qnode_measure', 'survey_id', nullable=False)
    op.drop_constraint('qnode_measure_pkey', 'qnode_measure',
        type_='primary')
    op.create_primary_key('qnode_measure_pkey', 'qnode_measure',
        ['program_id', 'survey_id', 'measure_id'])


def upgrade_response():
    # Change primary key of response from (id) to (submission_id, measure_id)
    op.add_column('response', sa.Column('survey_id', GUID()))
    op.add_column('response_history', sa.Column('survey_id', GUID()))
    op.add_column('attachment', sa.Column('submission_id', GUID()))
    op.add_column('attachment', sa.Column('measure_id', GUID()))

    op.execute("""
        UPDATE response AS r
        SET survey_id = sub.survey_id
        FROM submission AS sub
        WHERE sub.id = r.submission_id
        """)
    op.execute("""
        UPDATE response_history AS r
        SET survey_id = sub.survey_id
        FROM submission AS sub
        WHERE sub.id = r.submission_id
        """)
    op.execute("""
        UPDATE attachment AS a
        SET submission_id = r.submission_id, measure_id = r.measure_id
        FROM response AS r
        WHERE a.response_id = r.id
        """)

    op.drop_index('attachment_response_id_index', 'attachment')
    op.drop_index('response_submission_id_measure_id_index', 'response')
    op.execute("DROP INDEX IF EXISTS response_user_id_fkey1")
    op.drop_constraint('fk_attachment_response', 'attachment')
    op.drop_constraint('response_pkey', 'response', type_='primary')
    op.drop_constraint('response_history_pkey', 'response_history', type_='primary')
    op.drop_constraint('response_measure_id_assessment_id_key', 'response')
    op.create_primary_key('response_pkey', 'response',
        ['submission_id', 'measure_id'])
    op.create_primary_key('response_history_pkey', 'response_history',
        ['submission_id', 'measure_id', 'version'])
    op.create_foreign_key('response_qnode_measure_id_fkey',
        'response', 'qnode_measure',
        ['program_id', 'survey_id', 'measure_id'],
        ['program_id', 'survey_id', 'measure_id'])
    op.create_foreign_key('response_history_qnode_measure_id_fkey',
        'response_history', 'qnode_measure',
        ['program_id', 'survey_id', 'measure_id'],
        ['program_id', 'survey_id', 'measure_id'])
    op.drop_constraint('response_measure_id_fkey', 'response')
    op.drop_constraint('response_program_id_fkey', 'response')
    op.drop_constraint('response_history_measure_id_fkey', 'response_history')
    op.drop_constraint('response_history_program_id_fkey', 'response_history')
    op.create_foreign_key('fk_attachment_response',
        'attachment', 'response',
        ['submission_id', 'measure_id'],
        ['submission_id', 'measure_id'])
    op.create_index(
        'attachment_response_id_index', 'attachment',
        ['submission_id', 'measure_id'])
    op.drop_column('response', 'id')
    op.drop_column('response_history', 'id')
    op.drop_column('attachment', 'response_id')

    op.alter_column('response', 'survey_id', nullable=False)
    op.alter_column('response_history', 'survey_id', nullable=False)
    op.alter_column('attachment', 'submission_id', nullable=False)
    op.alter_column('attachment', 'measure_id', nullable=False)


def upgrade_rnode():
    op.drop_constraint('rnode_pkey', 'rnode', type_='primary')
    op.drop_constraint('rnode_qnode_id_assessment_id_key', 'rnode')
    op.drop_index('rnode_qnode_id_submission_id_index', 'rnode')
    op.drop_column('rnode', 'id')
    op.create_primary_key('rnode_pkey', 'rnode',
        ['submission_id', 'qnode_id'])


def upgrade_response_type():
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

    op.create_foreign_key('qnode_measure_survey_id_fkey',
        'qnode_measure', 'survey',
        ['survey_id', 'program_id'],
        ['id', 'program_id'])
    op.create_foreign_key('measure_response_type_id_fkey',
        'measure', 'response_type',
        ['response_type_id', 'program_id'],
        ['id', 'program_id'])
    op.alter_column('measure', 'response_type_id', nullable=False)
    op.drop_column('measure', 'response_type')
    op.drop_column('program', 'response_types')


def upgrade_activity():
    op.drop_constraint('activity_ob_type_check', 'activity', type_='check')
    op.drop_constraint('subscription_ob_type_check', 'subscription', type_='check')
    op.create_check_constraint(
        'activity_ob_type_check', 'activity',
        """ob_type = ANY (ARRAY[
            'organisation', 'user',
            'program', 'survey', 'qnode', 'measure', 'response_type',
            'submission', 'rnode', 'response'
        ])""")
    op.create_check_constraint(
        'subscription_ob_type_check', 'subscription',
        """ob_type = ANY (ARRAY[
            'organisation', 'user',
            'program', 'survey', 'qnode', 'measure', 'response_type',
            'submission', 'rnode', 'response'
        ])""")


def upgrade_errors():
    tables = ['program', 'survey', 'submission', 'qnode', 'rnode', 'qnode_measure', 'response']
    for table in tables:
        op.add_column(table, sa.Column('error', sa.TEXT()))
        # op.add_column(table, sa.Column('n_errors', sa.Integer()))
        # op.execute("UPDATE %s AS x SET n_errors = 0" % table)
        # op.alter_column(table, 'n_errors', nullable=False)


def downgrade():
    downgrade_errors()
    downgrade_variable()
    downgrade_activity()
    downgrade_response_type()
    downgrade_rnode()
    downgrade_response()
    downgrade_qnode_measure()


def downgrade_errors():
    tables = ['program', 'survey', 'submission', 'qnode', 'rnode', 'qnode_measure', 'response']
    for table in tables:
        op.drop_column(table, 'error')
        # op.drop_column(table, 'n_errors')


def downgrade_variable():
    op.drop_column('response', 'variables')
    op.drop_table('measure_variable')


def downgrade_response_type():
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
    op.drop_table('response_type')


def downgrade_rnode():
    op.drop_constraint('rnode_pkey', 'rnode', type_='primary')
    op.add_column('rnode', sa.Column('id', GUID()))

    op.execute("""
        UPDATE rnode AS rn
        SET id = md5(random()::text || clock_timestamp()::text)::uuid
        """)

    op.create_index(
        'rnode_qnode_id_submission_id_index', 'rnode',
        ['qnode_id', 'submission_id'])
    op.create_unique_constraint(
        'rnode_qnode_id_assessment_id_key', 'rnode',
        ['qnode_id', 'submission_id'])
    op.create_primary_key('rnode_pkey', 'rnode', ['id'])
    op.alter_column('rnode', 'id', nullable=False)


def downgrade_response():
    # Change primary key of response from (submission_id, measure_id) to (id)
    op.add_column('attachment', sa.Column('response_id', GUID()))
    op.add_column('response_history', sa.Column('id', GUID()))
    op.add_column('response', sa.Column('id', GUID()))
    op.drop_index('attachment_response_id_index', 'attachment')
    op.drop_constraint('fk_attachment_response','attachment')
    op.create_foreign_key('response_history_program_id_fkey',
        'response_history', 'program',
        ['program_id'],
        ['id'])
    op.create_foreign_key('response_history_measure_id_fkey',
        'response_history', 'measure',
        ['measure_id', 'program_id'],
        ['id', 'program_id'])
    op.create_foreign_key('response_program_id_fkey',
        'response', 'program',
        ['program_id'],
        ['id'])
    op.create_foreign_key('response_measure_id_fkey',
        'response', 'measure',
        ['measure_id', 'program_id'],
        ['id', 'program_id'])
    op.drop_constraint('response_history_qnode_measure_id_fkey', 'response_history')
    op.drop_constraint('response_qnode_measure_id_fkey', 'response')
    op.drop_constraint('response_history_pkey', 'response_history', type_='primary')
    op.drop_constraint('response_pkey', 'response', type_='primary')
    op.create_unique_constraint(
        'response_measure_id_assessment_id_key', 'response',
        ['measure_id', 'submission_id'])

    op.execute("""
        UPDATE response AS r
        SET id = md5(random()::text || clock_timestamp()::text)::uuid
        """)
    op.execute("""
        UPDATE response_history AS rh
        SET id = r.id
        FROM response AS r
        WHERE r.submission_id = rh.submission_id
            AND r.measure_id = rh.measure_id
        """)
    op.execute("""
        UPDATE attachment AS a
        SET response_id = r.id
        FROM response AS r
        WHERE a.submission_id = r.submission_id
            AND a.measure_id = r.measure_id
        """)

    op.create_primary_key('response_history_pkey', 'response_history',
        ['id', 'version'])
    op.create_primary_key('response_pkey', 'response',
        ['id'])
    op.create_foreign_key('fk_attachment_response',
        'attachment', 'response',
        ['response_id'],
        ['id'])
    op.create_index(
        'attachment_response_id_index', 'attachment',
        ['response_id'])
    op.create_index(
        'response_submission_id_measure_id_index', 'response',
        ['submission_id', 'measure_id'])
    # op.execute("""ALTER INDEX response_submission_id_measure_id_index
    #     RENAME TO response_assessment_id_measure_id_index""")

    op.drop_column('attachment', 'measure_id')
    op.drop_column('attachment', 'submission_id')
    op.drop_column('response_history', 'survey_id')
    op.drop_column('response', 'survey_id')

    op.alter_column('attachment', 'response_id', nullable=False)
    op.alter_column('response_history', 'id', nullable=False)
    op.alter_column('response', 'id', nullable=False)


def downgrade_qnode_measure():
    op.drop_column('qnode_measure', 'survey_id')
    op.create_primary_key('qnode_measure_pkey', 'qnode_measure',
        ['program_id', 'qnode_id', 'measure_id'])
    op.execute("""ALTER TABLE qnode_measure
        RENAME CONSTRAINT qnode_measure_qnode_id_fkey
        TO qnode_measure_link_qnode_id_fkey;""")
    op.execute("""ALTER TABLE qnode_measure
        RENAME CONSTRAINT qnode_measure_program_id_fkey
        TO qnode_measure_link_program_id_fkey;""")
    op.execute("""ALTER TABLE qnode_measure
        RENAME CONSTRAINT qnode_measure_measure_id_fkey
        TO qnode_measure_link_measure_id_fkey""")
    op.execute("""ALTER TABLE qnode_measure
        RENAME CONSTRAINT qnode_measure_pkey
        TO qnode_measure_link_pkey""")
    op.rename_table('qnode_measure', 'qnode_measure_link')


def downgrade_activity():
    op.drop_constraint('activity_ob_type_check', 'activity', type_='check')
    op.drop_constraint('subscription_ob_type_check', 'subscription', type_='check')
    op.create_check_constraint(
        'activity_ob_type_check', 'activity',
        """ob_type = ANY (ARRAY[
            'organisation', 'user',
            'program', 'survey', 'qnode', 'measure',
            'submission', 'rnode', 'response'
        ])""")
    op.create_check_constraint(
        'subscription_ob_type_check', 'subscription',
        """ob_type = ANY (ARRAY[
            'organisation', 'user',
            'program', 'survey', 'qnode', 'measure',
            'submission', 'rnode', 'response'
        ])""")

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
