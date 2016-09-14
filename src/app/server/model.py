import base64
from collections import namedtuple
from contextlib import contextmanager
from datetime import datetime
from itertools import chain, zip_longest
import logging
import os
import sys
import uuid

from sqlalchemy import Boolean, create_engine, Column, DateTime, Enum, Float, \
    ForeignKey, Index, Integer, String, Text, Table, LargeBinary
from sqlalchemy.dialects.postgresql import ARRAY, JSON
import sqlalchemy.exc
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.orm import backref, foreign, relationship, remote, \
    sessionmaker, validates
from sqlalchemy.orm.session import object_session
from sqlalchemy.schema import CheckConstraint, ForeignKeyConstraint, \
    Index, MetaData, UniqueConstraint
from sqlalchemy.sql import func
from passlib.hash import sha256_crypt
from voluptuous import All, Length, Schema
from voluptuous.humanize import validate_with_humanized_errors

from guid import GUID
from history_meta import Versioned, versioned_session
import response_type


log = logging.getLogger('app.model')
metadata = MetaData()
Base = declarative_base(metadata=metadata)


class ModelError(Exception):
    pass


def is_id(ob_or_id):
    return isinstance(ob_or_id, (str, uuid.UUID))


def to_id(ob_or_id):
    if ob_or_id is None:
        return None
    if is_id(ob_or_id):
        return ob_or_id
    return ob_or_id.id


ActionDescriptor = namedtuple(
    'ActionDescriptor',
    'message, ob_type, ob_ids, ob_refs')


class Observable:
    '''
    Mixin for mappers that can generate :py:class:`Activities <Activity>`.
    '''

    @property
    def ob_title(self):
        '''
        @return human-readable descriptive text for the object (e.g. its name).
        '''
        return self.title

    @property
    def ob_type(self):
        '''
        @return the type of object as a string.
        '''
        raise NotImplementedError()

    @property
    def ob_ids(self):
        '''
        @return a minimal list of IDs that uniquly identify the object, in
        descending order of specificity. E.g. [measure_id, program_id], because
        the measure belongs to the program.
        '''
        raise NotImplementedError()

    @property
    def action_lineage(self):
        '''
        @return a list of IDs that give a detailed path to the object, in order
        of increasing specificity. E.g.
        [program_id, survey_id, survey_id, qnode_id, qnode_id, measure_id]
        '''
        raise NotImplementedError()

    @property
    def action_descriptor(self):
        '''
        @return an ActionDescriptor for the object.
        '''
        return ActionDescriptor(
            self.ob_title,
            self.ob_type,
            self.ob_ids,
            [item.id for item in self.action_lineage])


class SystemConfig(Base):
    __tablename__ = 'systemconfig'
    name = Column(String, primary_key=True, nullable=False)
    value = Column(String)
    data = Column(LargeBinary)
    modified = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return "SystemConfig(name={}, value={})".format(self.name, self.value)


class Organisation(Observable, Base):
    __tablename__ = 'organisation'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)

    name = Column(Text, nullable=False)
    url = Column(Text, nullable=True)
    created = Column(DateTime, default=datetime.utcnow, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)

    @property
    def ob_title(self):
        return self.name

    @property
    def ob_type(self):
        return 'organisation'

    @property
    def ob_ids(self):
        return [self.id]

    @property
    def action_lineage(self):
        return [self]

    __table_args__ = (
        Index('organisation_name_key', func.lower(name), unique=True),
    )

    def __repr__(self):
        return "Organisation(name={})".format(self.name)


class OrgMeta(Base):
    __tablename__ = 'org_meta'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    organisation_id = Column(
        GUID, ForeignKey("organisation.id"), nullable=False)

    ownership = Column(Enum(
        'government run', 'government owned', 'private', 'shareholder',
        native_enum=False))
    structure = Column(Enum('internal', 'corporation', native_enum=False))
    asset_types = Column(ARRAY(Enum(
        'water wholesale', 'water local',
        'wastewater wholesale', 'wastewater local',
        native_enum=False)))
    regulation_level = Column(Enum(
        'extensive', 'partial', 'none', native_enum=False))

    value_water_ws = Column(Float)
    value_water_l = Column(Float)
    value_wastewater_ws = Column(Float)
    value_wastewater_l = Column(Float)

    operating_cost = Column(Float)
    revenue = Column(Float)
    number_fte = Column(Float)
    number_fte_ext = Column(Float)

    population_served = Column(Integer)
    number_of_customers = Column(Integer)
    volume_supplied = Column(Float)
    volume_collected = Column(Float)

    organisation = relationship(
        Organisation,
        backref=backref('meta', uselist=False, cascade="all, delete-orphan"))


class OrgLocation(Base):
    __tablename__ = 'org_location'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    organisation_id = Column(
        GUID, ForeignKey("organisation.id"), nullable=False)

    # Fields loosely match those returned by OSM's Nominatim service:
    # http://wiki.openstreetmap.org/wiki/Nominatim

    description = Column(Text, nullable=False)
    language = Column(Text)
    licence = Column(Text)

    country = Column(Text)
    # Region/prefecture/state district
    region = Column(Text)
    county = Column(Text)
    state = Column(Text)
    postcode = Column(Text)
    city = Column(Text)
    suburb = Column(Text)

    lon = Column(Float)
    lat = Column(Float)

    organisation = relationship(
        Organisation,
        backref=backref('locations', cascade="all, delete-orphan"))


ONE_DAY_S = 60 * 60 * 24


class AppUser(Observable, Base):
    __tablename__ = 'appuser'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    organisation_id = Column(
        GUID, ForeignKey("organisation.id"), nullable=False)

    email = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    password = Column(Text, nullable=False)
    role = Column(Enum(
            'admin', 'author', 'authority', 'consultant', 'org_admin', 'clerk',
            native_enum=False), nullable=False)
    created = Column(DateTime, default=datetime.utcnow, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)

    # Notification metadata.
    # NULL email_time means no notifications have ever been sent.
    email_time = Column(DateTime, nullable=True)
    # Email interval is the time between sending details of the activities a
    # user is subscribed to. Units are seconds. 0 means notifications are
    # disabled.
    email_interval = Column(Integer, default=ONE_DAY_S, nullable=False)

    def set_password(self, plaintext):
        self.password = sha256_crypt.encrypt(plaintext)

    def check_password(self, plaintext):
        return sha256_crypt.verify(plaintext, self.password)

    @property
    def ob_title(self):
        return self.name

    @property
    def ob_type(self):
        return 'user'

    @property
    def ob_ids(self):
        return [self.id]

    @property
    def action_lineage(self):
        return [self.organisation, self]

    __table_args__ = (
        Index('appuser_email_key', func.lower(email), unique=True),
        # Index on name because it's used for sorting
        Index('appuser_name_index', func.lower(name)),
        CheckConstraint(
            'email_interval BETWEEN 0 AND 1209600',
            name='appuser_email_interval_constraint'),
    )

    def __repr__(self):
        return "AppUser(email={})".format(self.email)


ROLE_HIERARCHY = {
    'admin': {'author', 'authority', 'consultant', 'org_admin', 'clerk'},
    'author': set(),
    'authority': {'consultant'},
    'consultant': set(),
    'org_admin': {'clerk'},
    'clerk': set()
}


def has_privillege(current_role, *target_roles):
    '''
    Checks whether one role has the privilleges of another role. For example,
        has_privillege('org_admin', 'clerk') -> True
        has_privillege('clerk', 'org_admin') -> False
        has_privillege('clerk', 'consultant', 'clerk') -> True
    '''
    for target_role in target_roles:
        if target_role == current_role:
            return True
        if target_role in ROLE_HIERARCHY[current_role]:
            return True
    return False


class Program(Observable, Base):
    __tablename__ = 'program'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    tracking_id = Column(GUID, default=uuid.uuid4, nullable=False)

    created = Column(DateTime, default=datetime.utcnow, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    # Program is not editable after being finalised.
    finalised_date = Column(DateTime)
    title = Column(Text, nullable=False)
    description = Column(Text)
    has_quality = Column(Boolean, default=False, nullable=False)
    hide_aggregate = Column(Boolean, default=False, nullable=False)
    error = Column(Text)

    @property
    def is_editable(self):
        return self.finalised_date is None

    @property
    def ob_type(self):
        return 'program'

    @property
    def ob_ids(self):
        return [self.id]

    @property
    def action_lineage(self):
        return [self]

    __table_args__ = (
        Index('program_tracking_id_index', tracking_id),
        Index('program_created_index', created),
    )

    def __repr__(self):
        return "Program(title={})".format(self.title)


class PurchasedSurvey(Base):
    __tablename__ = 'purchased_survey'
    program_id = Column(GUID, nullable=False, primary_key=True)
    survey_id = Column(GUID, nullable=False, primary_key=True)
    organisation_id = Column(GUID, nullable=False, primary_key=True)
    open_date = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ['survey_id', 'program_id'],
            ['survey.id', 'survey.program_id']
        ),
        ForeignKeyConstraint(
            ['program_id'],
            ['program.id']
        ),
        ForeignKeyConstraint(
            ['organisation_id'],
            ['organisation.id']
        ),
    )

    organisation = relationship(Organisation, backref='purchased_surveys')
    survey = relationship(
        'Survey', backref=backref(
            'purchased_surveys', passive_deletes=True, order_by=open_date.desc()))

    # This constructor is used by association_proxy when adding items to the
    # collection.
    def __init__(self, survey=None, organisation=None, **kwargs):
        self.survey = survey
        self.organisation = organisation
        super().__init__(**kwargs)


class Survey(Observable, Base):
    '''
    A collection of categories; root node in the program structure.
    '''
    __tablename__ = 'survey'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    program_id = Column(
        GUID, ForeignKey('program.id'), nullable=False, primary_key=True)

    n_measures = Column(Integer, default=0, nullable=False)

    title = Column(Text, nullable=False)
    description = Column(Text)
    modified = Column(DateTime, nullable=True)
    deleted = Column(Boolean, default=False, nullable=False)

    structure = Column(JSON, nullable=False)
    error = Column(Text)

    _structure_schema = Schema({
        'levels': All([
            {
                'title': All(str, Length(min=1)),
                'label': All(str, Length(min=1, max=2)),
                'has_measures': bool
            }
        ], Length(min=1)),
        'measure': {
            'title': All(str, Length(min=1)),
            'label': All(str, Length(min=1, max=2))
        }
    }, required=True)


    @validates('structure')
    def validate_structure(self, k, s):
        return validate_with_humanized_errors(s, Survey._structure_schema)

    @property
    def ordered_qnode_measures(self):
        '''Returns all measures in depth-first order'''
        for qnode in self.qnodes:
            yield from qnode.ordered_qnode_measures

    @property
    def min_stats_approval(self):
        '''
        @returns The minimum approval state for which it's OK to display
        statistical information
        '''
        return 'reviewed'

    @property
    def ob_type(self):
        return 'survey'

    @property
    def ob_ids(self):
        return [self.id, self.program_id]

    @property
    def action_lineage(self):
        return [self.program, self]

    def __repr__(self):
        return "Survey(title={}, program={})".format(
            self.title, getattr(self.program, 'title', None))


Survey.organisations = association_proxy('purchased_surveys', 'organisation')
Organisation.surveys = association_proxy('purchased_surveys', 'survey')


class QuestionNode(Observable, Base):
    '''
    A program category; contains sub-categories and measures. Gives a program its
    structure. Both measures and sub-categories are ordered.
    '''
    __tablename__ = 'qnode'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    program_id = Column(GUID, nullable=False, primary_key=True)
    survey_id = Column(GUID, nullable=False)
    parent_id = Column(GUID)

    deleted = Column(Boolean, default=False, nullable=False)
    seq = Column(Integer)
    n_measures = Column(Integer, default=0, nullable=False)
    total_weight = Column(Float, default=0, nullable=False)
    error = Column(Text)

    title = Column(Text, nullable=False)
    description = Column(Text)

    __table_args__ = (
        ForeignKeyConstraint(
            ['parent_id', 'program_id'],
            ['qnode.id', 'qnode.program_id']
        ),
        ForeignKeyConstraint(
            ['survey_id', 'program_id'],
            ['survey.id', 'survey.program_id']
        ),
        ForeignKeyConstraint(
            ['program_id'],
            ['program.id']
        ),
        Index('qnode_parent_id_program_id_index', parent_id, program_id),
        Index('qnode_survey_id_program_id_index', survey_id, program_id),
    )

    program = relationship(Program)

    def get_rnode(self, submission, create=False):
        sid = to_id(submission)
        rnode = (object_session(self).query(ResponseNode)
            .get((sid, self.id)))
        if not rnode and create:
            rnode = ResponseNode(program=self.program, qnode=self)
            rnode.submission_id = sid
            object_session(self).add(rnode)
            # Without this flush, rnode.responses may be incomplete. Test with
            # test_daemon.DaemonTest.
            # TODO: Perahps this could be avoided if the recalculation was done
            # in two stages: first create required rnodes, then flush, then
            # update their scores?
            object_session(self).flush()
        return rnode

    def lineage(self):
        if self.parent_id:
            return self.parent.lineage() + [self]
        else:
            return [self]

    def get_path(self):
        return " ".join(["%d." % (q.seq + 1) for q in self.lineage()])

    def any_deleted(self):
        return self.deleted or self.parent_id and self.parent.any_deleted()

    @property
    def ordered_qnode_measures(self):
        '''Returns all qnode/measures in depth-first order'''
        for child in self.children:
            yield from child.ordered_qnode_measures
        yield from self.qnode_measures

    @property
    def ob_type(self):
        return 'qnode'

    @property
    def ob_ids(self):
        return [self.id, self.program_id]

    @property
    def action_lineage(self):
        return [self.program, self.survey] + self.lineage()

    def __repr__(self):
        return "QuestionNode(path={}, title={}, program={})".format(
            self.get_path(), self.title,
            getattr(self.program, 'title', None))


class Measure(Observable, Base):
    __tablename__ = 'measure'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    program_id = Column(GUID, nullable=False, primary_key=True)
    response_type_id = Column(GUID, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)

    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    weight = Column(Float, nullable=False)

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

    program = relationship(
        Program, backref=backref('measures', passive_deletes=True))

    @property
    def parents(self):
        return (qm.qnode for qm in self.qnode_measures)

    def get_parent(self, survey):
        qnode_measure = self.get_qnode_measure(survey)
        return qnode_measure and qnode_measure.qnode or None

    def get_qnode_measure(self, survey):
        sid = to_id(survey)
        return (object_session(self).query(QnodeMeasure)
            .get((self.program_id, sid, self.id)))

    def get_path(self, survey):
        qm = self.get_qnode_measure(survey)
        return qm and qm.get_path() or None

    def lineage(self, survey=None):
        survey_id = to_id(survey)

        if survey_id:
            qms = [qm for qm in self.qnode_measures
                   if str(qm.survey_id) == str(survey_id)]
        else:
            qms = self.qnode_measures

        lineages = [reversed(qm.qnode.lineage()) for qm in qms]
        mixed_lineage = chain(*list(zip_longest(*lineages)))
        mixed_lineage = [q for q in mixed_lineage
                         if q is not None]
        mixed_lineage = list(reversed(mixed_lineage))

        return mixed_lineage + [self]

    @property
    def ob_type(self):
        return 'measure'

    @property
    def ob_ids(self):
        return [self.id, self.program_id]

    @property
    def action_lineage(self):
        hs = [qm.survey for qm in self.qnode_measures]
        return [self.program] + hs + self.lineage()

    def __repr__(self):
        return "Measure(title={}, program={})".format(
            self.title, getattr(self.program, 'title', None))


class QnodeMeasure(Base):
    # This is an association object for qnodes <-> measures. Normally this would
    # be done with a raw table, but because we want access to the `seq` column,
    # it needs to be a mapped class.
    __tablename__ = 'qnode_measure'
    program_id = Column(GUID, nullable=False, primary_key=True)
    survey_id = Column(GUID, nullable=False, primary_key=True)
    measure_id = Column(GUID, nullable=False, primary_key=True)
    qnode_id = Column(GUID, nullable=False)

    seq = Column(Integer)
    error = Column(Text)

    __table_args__ = (
        ForeignKeyConstraint(
            ['qnode_id', 'program_id'],
            ['qnode.id', 'qnode.program_id']
        ),
        ForeignKeyConstraint(
            ['measure_id', 'program_id'],
            ['measure.id', 'measure.program_id']
        ),
        ForeignKeyConstraint(
            ['survey_id', 'program_id'],
            ['survey.id', 'survey.program_id']
        ),
        ForeignKeyConstraint(
            ['program_id'],
            ['program.id']
        ),
        Index('qnodemeasure_qnode_id_program_id_index', qnode_id, program_id),
        Index('qnodemeasure_measure_id_program_id_index', measure_id, program_id),
    )

    program = relationship(Program)

    def __init__(self, program=None, survey=None, qnode=None, measure=None,
                 **kwargs):
        # if qnode:
        #     raise ModelError(
        #         "Construction using a qnode is not allowed. Append the new"
        #         " QnodeMeasure to qnode.qnode_measures instead, to ensure"
        #         " the seq field is set correctly.")
        super().__init__(
            program=program, survey=survey, qnode=qnode, measure=measure,
            **kwargs)

    def get_path(self):
        return "%s %d." % (self.qnode.get_path(), self.seq + 1)

    def get_response(self, submission):
        submission_id = to_id(submission)
        return (object_session(self).query(Response)
            .get((submission_id, self.measure_id)))

    def __repr__(self):
        return "QnodeMeasure(path={}, program={}, survey={}, measure={})".format(
            self.get_path(),
            getattr(self.program, 'title', None),
            getattr(self.survey, 'title', None),
            getattr(self.measure, 'title', None))


class ResponseType(Observable, Base):
    __tablename__ = 'response_type'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    program_id = Column(
        GUID, ForeignKey("program.id"), nullable=False, primary_key=True)

    name = Column(Text, nullable=False)
    parts = Column(JSON, nullable=False)
    formula = Column(Text)

    __table_args__ = (
        ForeignKeyConstraint(
            ['program_id'],
            ['program.id']),
        Index(
            'response_type_target_program_id_id_index',
            'program_id', 'id'),
        UniqueConstraint('program_id', 'name'),
    )

    program = relationship(Program)

    @validates('parts')
    def validate_parts(self, k, parts):
        parts = validate_with_humanized_errors(
            parts, response_type.response_parts_schema)
        response_type.validate_parts(parts)
        return parts

    @validates('formula')
    def validate_parts(self, k, formula):
        response_type.validate_formula(formula)
        return formula

    @property
    def n_measures(self):
        return object_session(self).query(Measure).with_parent(self).count()

    @property
    def ob_title(self):
        return self.name

    @property
    def ob_type(self):
        return 'response_type'

    @property
    def ob_ids(self):
        return [self.id, self.program_id]

    @property
    def action_lineage(self):
        return [self.program, self]

    def __repr__(self):
        return "ResponseType(name={}, program={})".format(
            self.name, getattr(self.program, 'title', None))


class MeasureVariable(Base):
    # This is an association object for measures <-> measures, so that external
    # variables in a response type can be bound to another measure.
    __tablename__ = 'measure_variable'
    program_id = Column(GUID, nullable=False, primary_key=True)
    survey_id = Column(GUID, nullable=False, primary_key=True)
    target_measure_id = Column(GUID, nullable=False, primary_key=True)
    target_field = Column(Text, nullable=False, primary_key=True)

    source_measure_id = Column(GUID, nullable=False, primary_key=True)
    source_field = Column(Text, primary_key=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ['target_measure_id', 'program_id'],
            ['measure.id', 'measure.program_id']),
        ForeignKeyConstraint(
            ['source_measure_id', 'program_id'],
            ['measure.id', 'measure.program_id']),
        ForeignKeyConstraint(
            ['survey_id', 'program_id'],
            ['survey.id', 'survey.program_id']),
        ForeignKeyConstraint(
            ['program_id'],
            ['program.id']),
        Index(
            'measure_variable_program_id_target_measure_id_index',
            'program_id', 'target_measure_id'),
        Index(
            'measure_variable_program_id_source_measure_id_index',
            'program_id', 'source_measure_id'),
    )

    program = relationship(Program)

    def __repr__(self):
        return "MeasureVariable({}#{} <- {}#{}, program={})".format(
            self.source_qnode_measure.get_path(),
            self.source_field,
            self.target_qnode_measure.get_path(),
            self.target_field,
            getattr(self.program, 'title', None))


class Submission(Observable, Base):
    __tablename__ = 'submission'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    program_id = Column(GUID, nullable=False)
    organisation_id = Column(GUID, nullable=False)
    survey_id = Column(GUID, nullable=False)

    title = Column(Text)
    approval = Column(
        Enum('draft', 'final', 'reviewed', 'approved', native_enum=False),
        nullable=False)
    created = Column(DateTime, default=datetime.utcnow, nullable=False)
    modified = Column(DateTime, nullable=True)
    deleted = Column(Boolean, default=False, nullable=False)
    error = Column(Text)

    __table_args__ = (
        ForeignKeyConstraint(
            ['survey_id', 'program_id'],
            ['survey.id', 'survey.program_id']
        ),
        ForeignKeyConstraint(
            ['program_id'],
            ['program.id']
        ),
        ForeignKeyConstraint(
            ['organisation_id'],
            ['organisation.id']
        ),
        Index('submission_organisation_id_survey_id_index',
              organisation_id, survey_id),
    )

    program = relationship(Program)
    organisation = relationship(Organisation)

    @property
    def ordered_responses(self):
        '''Returns all responses in depth-first order'''
        for qnode_measure in self.survey.ordered_qnode_measures:
            response = qnode_measure.get_response(self)
            if response is not None:
                yield response

    @property
    def rnodes(self):
        for qnode in self.survey.qnodes:
            rnode = qnode.get_rnode(self)
            if rnode is not None:
                yield rnode

    @property
    def ob_type(self):
        return 'submission'

    @property
    def ob_ids(self):
        return [self.id]

    @property
    def action_lineage(self):
        # It would be nice to include the program and survey in this list, but
        # then everyone who was subscribed to a survey would get spammed with
        # all the submissions against it.
        return [self.organisation, self]

    def __repr__(self):
        return "Submission(program={}, org={})".format(
            getattr(self.program, 'title', None),
            getattr(self.organisation, 'name', None))


class ResponseNode(Observable, Base):
    __tablename__ = 'rnode'
    submission_id = Column(GUID, nullable=False, primary_key=True)
    qnode_id = Column(GUID, nullable=False, primary_key=True)
    program_id = Column(GUID, nullable=False)

    n_draft = Column(Integer, default=0, nullable=False)
    n_final = Column(Integer, default=0, nullable=False)
    n_reviewed = Column(Integer, default=0, nullable=False)
    n_approved = Column(Integer, default=0, nullable=False)
    n_not_relevant = Column(Integer, default=0, nullable=False)
    score = Column(Float, default=0.0, nullable=False)
    error = Column(Text)

    importance = Column(Float)
    urgency = Column(Float)
    max_importance = Column(Float, default=0.0, nullable=False)
    max_urgency = Column(Float, default=0.0, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ['qnode_id', 'program_id'],
            ['qnode.id', 'qnode.program_id']
        ),
        ForeignKeyConstraint(
            ['program_id'],
            ['program.id']
        ),
        ForeignKeyConstraint(
            ['submission_id'],
            ['submission.id']
        ),
        UniqueConstraint('qnode_id', 'submission_id'),
        Index('rnode_qnode_id_submission_id_index', qnode_id, submission_id),
    )

    program = relationship(Program)
    submission = relationship(Submission)

    @property
    def parent(self):
        if self.qnode.parent is None:
            return None
        return self.qnode.parent.get_rnode(self.submission)

    @property
    def children(self):
        for child_qnode in self.qnode.children:
            rnode = child_qnode.get_rnode(self.submission)
            if rnode is not None:
                yield rnode

    @property
    def ordered_responses(self):
        '''Returns all responses in depth-first order'''
        for child in self.children:
            for response in child.ordered_responses:
                yield response
        for response in self.responses:
            yield response

    @property
    def responses(self):
        for qnode_measure in self.qnode.qnode_measures:
            response = qnode_measure.get_response(self.submission)
            if response is not None:
                yield response

    def lineage(self):
        return [q.get_rnode(self.submission_id) for q in self.qnode.lineage()]

    @property
    def ob_type(self):
        return 'rnode'

    @property
    def ob_title(self):
        return self.qnode.title

    @property
    def ob_ids(self):
        return [self.qnode_id, self.submission_id]

    @property
    def action_lineage(self):
        # It would be nice to include the program and survey in this list, but
        # then everyone who was subscribed to a survey would get spammed with
        # all the submissions against it.
        return [self.submission.organisation, self.submission] + self.lineage()

    @property
    def action_descriptor(self):
        # Use qnodes instead of rnodes for lineage, because rnode.id is not part
        # of the API.
        lineage = ([self.submission.id] +
                   [q.id for q in self.qnode.lineage()])
        return ActionDescriptor(
            self.ob_title, self.ob_type, self.ob_ids, lineage)

    def __repr__(self):
        org = getattr(self.submission, 'organisation', None)
        return "ResponseNode(path={}, submission={}, org={})".format(
            self.qnode and self.qnode.get_path() or None,
            getattr(self.submission, 'title', None),
            getattr(org, 'name', None))


class Response(Observable, Versioned, Base):
    __tablename__ = 'response'
    submission_id = Column(GUID, nullable=False, primary_key=True)
    measure_id = Column(GUID, nullable=False, primary_key=True)
    program_id = Column(GUID, nullable=False)
    survey_id = Column(GUID, nullable=False)
    user_id = Column(GUID, nullable=False)

    comment = Column(Text, nullable=False)
    not_relevant = Column(Boolean, nullable=False)
    response_parts = Column(JSON, nullable=False)
    audit_reason = Column(Text)
    modified = Column(DateTime, nullable=False)
    quality = Column(Float)
    approval = Column(
        Enum('draft', 'final', 'reviewed', 'approved', native_enum=False),
        nullable=False)

    # Fields derived from response_parts
    score = Column(Float, default=0.0, nullable=False)
    variables = Column(JSON, default=dict, nullable=False)
    error = Column(Text)

    __table_args__ = (
        ForeignKeyConstraint(
            ['program_id', 'survey_id', 'measure_id'],
            ['qnode_measure.program_id', 'qnode_measure.survey_id', 'qnode_measure.measure_id'],
            info={'version': True}
        ),
        ForeignKeyConstraint(
            ['user_id'],
            ['appuser.id'],
            info={'version': True}
        ),
        ForeignKeyConstraint(
            ['submission_id'],
            ['submission.id'],
            info={'version': True}
        ),
        Index('response_submission_id_measure_id_index',
              submission_id, measure_id),
    )

    user = relationship(AppUser)

    @property
    def parent(self):
        return self.qnode_measure.qnode.get_rnode(self.submission)

    @validates('response_parts')
    def validate_response_parts(self, k, s):
        return validate_with_humanized_errors(s, response_type.response_schema)

    def lineage(self):
        return ([q.get_rnode(self.submission_id)
                 for q in self.qnode_measure.qnode.lineage()] +
                [self])

    @property
    def ob_type(self):
        return 'response'

    @property
    def ob_title(self):
        return self.measure.title

    @property
    def ob_ids(self):
        return [self.measure_id, self.submission_id]

    @property
    def action_lineage(self):
        # It would be nice to include the program and survey in this list, but
        # then everyone who was subscribed to a survey would get spammed with
        # all the submissions against it.
        return [self.submission.organisation, self.submission] + self.lineage()

    @property
    def action_descriptor(self):
        # Use qnodes and the measure instead of rnodes and the response for
        # lineage, because rnode.id is not part of the API, and response has
        # no ID of its own.
        lineage = ([self.submission.id] +
                   [q.id for q in self.qnode_measure.qnode.lineage()] +
                   [self.measure_id])
        return ActionDescriptor(
            self.ob_title, self.ob_type, self.ob_ids, lineage)

    def __repr__(self):
        org = getattr(self.submission, 'organisation', None)
        return "Response(path={}, submission={}, org={})".format(
            self.qnode_measure.get_path(),
            getattr(self.submission, 'title', None),
            getattr(org, 'name', None))


ResponseHistory = Response.__history_mapper__.class_
ResponseHistory.response_parts = Response.response_parts


class Attachment(Base):
    __tablename__ = 'attachment'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    organisation_id = Column(
        GUID, ForeignKey("organisation.id"), nullable=False)
    submission_id = Column(GUID, nullable=False)
    measure_id = Column(GUID, nullable=False)

    storage = Column(
        Enum('external', 'aws', 'database', native_enum=False),
        nullable=False)
    file_name = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
    blob = Column(LargeBinary, nullable=True)

    __table_args__ = (
        Index('attachment_response_id_index', submission_id, measure_id),
        ForeignKeyConstraint(
            ['submission_id', 'measure_id'],
            ['response.submission_id', 'response.measure_id']
        ),
    )

    response = relationship(Response, backref='attachments')
    organisation = relationship(Organisation)


class Activity(Base):
    '''
    An event in the activity stream (timeline). This forms a kind of logging
    that can be filtered based on users' subscriptions.
    '''
    __tablename__ = 'activity'
    id = Column(GUID, default=uuid.uuid4, nullable=False, primary_key=True)
    created = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Subject is the user performing the action. The object may also be a user.
    subject_id = Column(GUID, ForeignKey("appuser.id"), nullable=False)
    # Verb is the action being performed by the subject on the object.
    verbs = Column(
        ARRAY(Enum(
            'broadcast',
            'create', 'update', 'state', 'delete', 'undelete',
            'relation', 'reorder_children',
            native_enum=False)),
        nullable=False)
    # A snapshot of some defining feature of the object at the time the event
    # happened (e.g. title of a measure before it was deleted).
    message = Column(Text)
    sticky = Column(Boolean, nullable=False, default=False)

    # Object reference (the entity being acted upon). The ob_type and ob_id_*
    # columns are for looking up the target object (e.g. to create a hyperlink).
    ob_type = Column(Enum(
        'organisation', 'user',
        'program', 'survey', 'qnode', 'measure', 'response_type',
        'submission', 'rnode', 'response',
        native_enum=False))
    ob_ids = Column(ARRAY(GUID), nullable=False)
    # The ob_refs column contains all relevant IDs including e.g. parent
    # categories, and is used for filtering.
    ob_refs = Column(ARRAY(GUID), nullable=False)

    __table_args__ = (
        # Index `created` column to allow fast filtering by date ranges across
        # all users.
        # Note Postgres' default index is btree, which supports ordered index
        # scanning.
        Index('activity_created_index', created),
        # A multi-column index that has the subject's ID first, so we can
        # quickly list the recent activity of a user.
        Index('activity_subject_id_created_index', subject_id, created),
        # Sticky activities are queried without respect to time, so a separate
        # index is needed for them.
        Index('activity_sticky_index', sticky,
              postgresql_where=(sticky == True)),
        CheckConstraint(
            "(verbs @> ARRAY['broadcast']::varchar[] or ob_type != null)",
            name='activity_broadcast_constraint'),
        CheckConstraint(
            'ob_type = null or array_length(verbs, 1) > 0',
            name='activity_verbs_length_constraint'),
        CheckConstraint(
            'ob_type = null or array_length(ob_ids, 1) > 0',
            name='activity_ob_ids_length_constraint'),
        CheckConstraint(
            'ob_type = null or array_length(ob_refs, 1) > 0',
            name='activity_ob_refs_length_constraint'),
    )

    subject = relationship(AppUser)


class Subscription(Base):
    '''Subscribes a user to events related to some object'''
    __tablename__ = 'subscription'
    id = Column(GUID, default=uuid.uuid4, nullable=False, primary_key=True)
    created = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_id = Column(GUID, ForeignKey("appuser.id"), nullable=False)
    subscribed = Column(Boolean, nullable=False)

    # Object reference; does not include parent objects. One day an index might
    # be needed on the ob_refs column; if you want to use GIN, see:
    # http://www.postgresql.org/docs/9.4/static/gin-intro.html
    # http://stackoverflow.com/questions/19959735/postgresql-gin-index-on-array-of-uuid
    ob_type = Column(Enum(
        'organisation', 'user',
        'program', 'survey', 'qnode', 'measure', 'response_type',
        'submission', 'rnode', 'response',
        native_enum=False))
    ob_refs = Column(ARRAY(GUID), nullable=False)

    __table_args__ = (
        # Index to allow quick lookups of subscribed objects for a given user
        Index('subscription_user_id_index', user_id),
        UniqueConstraint(
            user_id, ob_refs,
            name='subscription_user_ob_refs_unique_constraint'),
        CheckConstraint(
            'ob_type = null or array_length(ob_refs, 1) > 0',
            name='subscription_ob_refs_length_constraint'),
    )

    user = relationship(AppUser, backref='subscriptions')


# Lists and Complex Relationships
#
# We need to give explicit join rules due to use of foreign key in composite
# primary keys. The foreign_keys argument is used to mark which columns are
# writable. For example, where a class has a program relationship that can write
# to the program_id column, the foreign_keys list for other relationships will
# not include the program_id column so that there is no ambiguity when both
# relationships are written to.
# http://docs.sqlalchemy.org/en/rel_1_0/orm/join_conditions.html#overlapping-foreign-keys
#
# Addtitionally, self-referential relationships (trees) need the remote_side
# argument.
# http://docs.sqlalchemy.org/en/rel_1_0/orm/self_referential.html#composite-adjacency-lists


# Use verbose back_populates instead of backref because the relationships are
# asymmetric: a deleted survey still has a program, but a program has no
# deleted surveys.
#
# http://docs.sqlalchemy.org/en/latest/orm/backref.html#one-way-backrefs
#
# It is therefore possible to create an inconsistent in-memory model:
#
#     s = Program(title="Program 1")
#     h = Survey(title="Survey 1", deleted=True)
#     s.surveys.append(h)
#     print(s.surveys)
#     # prints [Survey(title=Survey 1, program=Program 1)]
#
# After calling `session.flush()`, the list of surveys will be empty.
# Maintaining consistency is the responsibility of the programmer. In this
# example, the programmer should have either:
#
#  - Not set `h.deleted = True`, to avoid violating the join condition.
#  - Used `h.program = s`, which does not back-populate `Program.surveys`.
#
# When soft-deleting an entry, the programmer should:
#
#  1. Set `h.deleted = True`.
#  2. Remove it from the collection with `s.surveys.remove(h)`.
#  3. Reinstate the link to the owning program with `h.program = s`.


AppUser.organisation = relationship(Organisation)

Organisation.users = relationship(
    AppUser, back_populates="organisation", passive_deletes=True,
    primaryjoin=(Organisation.id == AppUser.organisation_id) &
                (AppUser.deleted == False))


Survey.program = relationship(Program)

Program.surveys = relationship(
    Survey, back_populates='program', passive_deletes=True,
    order_by='Survey.title',
    primaryjoin=(Program.id == Survey.program_id) &
                (Survey.deleted == False))


# The link from a node to a survey uses a one-way backref for another reason.
# We don't want modifications to this attribute to affect the other side of the
# relationship: otherwise non-root nodes couldn't have their surveys set
# easily.
# http://docs.sqlalchemy.org/en/latest/orm/backref.html#one-way-backrefs
QuestionNode.survey = relationship(
    Survey,
    primaryjoin=(foreign(QuestionNode.survey_id) == remote(Survey.id)) &
                (QuestionNode.program_id == remote(Survey.program_id)))


# "Children" of the survey: these are roots of the qnode tree. Use
# back_populates instead of backref for the reasons described above.
Survey.qnodes = relationship(
    QuestionNode, back_populates='survey', passive_deletes=True,
    order_by=QuestionNode.seq, collection_class=ordering_list('seq'),
    primaryjoin=(foreign(QuestionNode.survey_id) == Survey.id) &
                (QuestionNode.program_id == Survey.program_id) &
                (QuestionNode.parent_id == None) &
                (QuestionNode.deleted == False))


# The remote_side argument needs to be set on the many-to-one side, so it's
# easier to define this relationship from the perspective of the child, i.e.
# as QuestionNode.parent instead of QuestionNode.children. The backref still
# works. The collection arguments (passive_deletes, order_by, etc) need to be
# placed on the one-to-many side, so they are nested in the backref argument.
QuestionNode.parent = relationship(
    QuestionNode,
    primaryjoin=(foreign(QuestionNode.parent_id) == remote(QuestionNode.id)) &
                (QuestionNode.program_id == remote(QuestionNode.program_id)))


QuestionNode.children = relationship(
    QuestionNode, back_populates='parent', passive_deletes=True,
    order_by=QuestionNode.seq, collection_class=ordering_list('seq'),
    primaryjoin=(foreign(remote(QuestionNode.parent_id)) == QuestionNode.id) &
                (remote(QuestionNode.program_id) == QuestionNode.program_id) &
                (remote(QuestionNode.deleted) == False))


QuestionNode.qnode_measures = relationship(
    QnodeMeasure, backref='qnode', cascade='all, delete-orphan',
    order_by=QnodeMeasure.seq, collection_class=ordering_list('seq'),
    primaryjoin=(foreign(QnodeMeasure.qnode_id) == QuestionNode.id) &
                (QnodeMeasure.program_id == QuestionNode.program_id))


Measure.qnode_measures = relationship(
    QnodeMeasure, backref='measure',
    primaryjoin=(foreign(QnodeMeasure.measure_id) == Measure.id) &
                (QnodeMeasure.program_id == Measure.program_id))


QnodeMeasure.survey = relationship(
    Survey,
    primaryjoin=(foreign(QnodeMeasure.survey_id) == remote(Survey.id)) &
                (QnodeMeasure.program_id == remote(Survey.program_id)))


#
# Suppose qnode_measure_a is a dependency of qnode_measure_b. Then:
#
#     qnode_measure_a.target = measure_variable_ab
#     mes_variable_ab.source_qnode_measure = qnode_measure_a
#     mes_variable_ab.target_qnode_measure = qnode_measure_b
#     qnode_measure_b.source = measure_variable_ab
#
#    ┌─────────────────────┐  ┌────────────────────┐  ┌─────────────────────┐
#    │   QnodeMeasure A    │  │ MeasureVariable AB │  │   QnodeMeasure B    │
#    ╞═════════════════════╡  ╞════════════════════╡  ╞═════════════════════╡
#  x━┥ sources     targets ┝━━┥ source      target ┝━━┥ sources     targets ┝━x
#    └─────────────────────┘  └────────────────────┘  └─────────────────────┘
#

# Dependencies - yes, the source is the target. It's funny how that is.
QnodeMeasure.target_vars = relationship(
    MeasureVariable, backref='source_qnode_measure',
    primaryjoin=(foreign(MeasureVariable.source_measure_id) == QnodeMeasure.measure_id) &
                (MeasureVariable.survey_id == QnodeMeasure.survey_id) &
                (MeasureVariable.program_id == QnodeMeasure.program_id))

# Dependants - yes, the target is the source. It's funny how that is.
QnodeMeasure.source_vars = relationship(
    MeasureVariable, backref='target_qnode_measure',
    primaryjoin=(foreign(MeasureVariable.target_measure_id) == QnodeMeasure.measure_id) &
                (MeasureVariable.survey_id == QnodeMeasure.survey_id) &
                (MeasureVariable.program_id == QnodeMeasure.program_id))


MeasureVariable.survey = relationship(
    Survey,
    primaryjoin=(foreign(MeasureVariable.survey_id) == Survey.id) &
                (MeasureVariable.program_id == Survey.program_id))


Measure.response_type = relationship(
    ResponseType,
    primaryjoin=(foreign(Measure.response_type_id) == ResponseType.id) &
                (ResponseType.program_id == Measure.program_id))

ResponseType.measures = relationship(
    Measure, back_populates='response_type', passive_deletes=True,
    primaryjoin=(foreign(Measure.response_type_id) == ResponseType.id) &
                (ResponseType.program_id == Measure.program_id))


Submission.survey = relationship(
    Survey,
    primaryjoin=(foreign(Submission.survey_id) == Survey.id) &
                (Submission.program_id == Survey.program_id))

Submission.responses = relationship(
    Response, backref='submission', passive_deletes=True)


ResponseNode.qnode = relationship(
    QuestionNode,
    primaryjoin=(foreign(ResponseNode.qnode_id) == QuestionNode.id) &
                (ResponseNode.program_id == QuestionNode.program_id))


Response.qnode_measure = relationship(
    QnodeMeasure)
    # primaryjoin=(foreign(Response.measure_id) == Measure.id) &
    #             (Response.program_id == Measure.program_id))

Response.measure = association_proxy('qnode_measure', 'measure')


ResponseHistory.user = relationship(
    AppUser, backref='user', passive_deletes=True)


Session = None
VersionedSession = None
ReadonlySession = None


@contextmanager
def session_scope(version=False, readonly=False):
    # http://docs.sqlalchemy.org/en/latest/orm/session_basics.html#when-do-i-construct-a-session-when-do-i-commit-it-and-when-do-i-close-it
    """Provide a transactional scope around a series of operations."""
    if readonly:
        session = ReadonlySession()
    elif version:
        session = VersionedSession()
    else:
        session = Session()

    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


def create_analyst_user():
    '''
    For arbitary queries on the web, create a new user named 'analyst'
    and give SELECT permission to all tables except the appuser.password
    column.
    '''

    with session_scope() as session:
        password = base64.b32encode(os.urandom(30)).decode('ascii')
        store_analyst_password(password, session)
        session.execute(
            "CREATE USER analyst WITH PASSWORD :pwd", {'pwd': password})
        session.execute(
            "GRANT USAGE ON SCHEMA public TO analyst")
        session.execute(
            "GRANT SELECT"
            " (id, organisation_id, email, name, role, created, deleted,"
            "  email_time, email_interval)"
            " ON appuser TO analyst")
        for table in Base.metadata.tables:
            if str(table) not in {'appuser', 'systemconfig', 'alembic_version'}:
                session.execute(
                    "GRANT SELECT ON {} TO analyst".format(table))


def reset_analyst_password():
     with session_scope() as session:
        password = base64.b32encode(os.urandom(30)).decode('ascii')
        store_analyst_password(password, session)
        session.execute(
            "ALTER ROLE analyst WITH PASSWORD :pwd", {'pwd': password})


def store_analyst_password(password, session):
    pwd_conf = session.query(SystemConfig).get('_analyst_password')
    if pwd_conf is None:
        pwd_conf = SystemConfig(name='_analyst_password')
        pwd_conf.human_name = "Analyst password"
        pwd_conf.description = "Password for read-only database access"
        pwd_conf.user_defined = False
        session.add(pwd_conf)
    pwd_conf.value = password


def connect_db(url):
    global Session, VersionedSession
    engine = create_engine(url)
    # Never drop the schema here.
    # - For short-term testing, use psql.
    # - For breaking changes, add migration code to the alembic scripts.
    Session = sessionmaker(bind=engine)
    VersionedSession = sessionmaker(bind=engine)
    versioned_session(VersionedSession)

    return engine


class MissingUser(ModelError):
    pass


class WrongPassword(ModelError):
    pass


def connect_db_ro(base_url):
    global ReadonlySession

    with session_scope() as session:
        count = (session.execute(
                '''SELECT count(*)
                   FROM pg_catalog.pg_user u
                   WHERE u.usename = :usename''',
                {'usename': 'analyst'})
            .scalar())
        if count != 1:
            raise MissingUser("analyst user does not exist")

        password = (session.query(SystemConfig.value)
                .filter(SystemConfig.name == '_analyst_password')
                .scalar())

    parsed_url = sqlalchemy.engine.url.make_url(base_url)
    readonly_url = sqlalchemy.engine.url.URL(
        parsed_url.drivername,
        username='analyst',
        password=password,
        host=parsed_url.host,
        port=parsed_url.port,
        database=parsed_url.database)
    engine_readonly = create_engine(readonly_url)
    ReadonlySession = sessionmaker(bind=engine_readonly)

    # Try to connect now so we know if the password is OK
    with session_scope(readonly=True) as session:
        try:
            count = session.query(Program).count()
        except sqlalchemy.exc.OperationalError as e:
            raise WrongPassword(e)

    return engine_readonly


def initialise_schema(engine):
    Base.metadata.create_all(engine)
    # Analyst user creation *must* be done here. Schema upgrades need to adjust
    # permissions of the analyst user, therefore that user is part of the
    # schema.
    create_analyst_user()
