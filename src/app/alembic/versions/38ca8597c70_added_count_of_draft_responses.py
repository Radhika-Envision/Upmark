"""Added count of draft responses

Revision ID: 38ca8597c70
Revises: 4ec77533136
Create Date: 2016-05-09 06:42:02.238151

"""

# revision identifiers, used by Alembic.
revision = '38ca8597c70'
down_revision = '4ec77533136'
branch_labels = None
depends_on = None

import logging
import time

from alembic import op
import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import foreign, relationship, remote, sessionmaker
from sqlalchemy.schema import ForeignKeyConstraint, MetaData


metadata = MetaData()
Base = declarative_base(metadata=metadata)
Session = sessionmaker()

log_migration = logging.getLogger('app.migration')


def upgrade():
    op.add_column('rnode', sa.Column('n_draft', sa.Integer()))
    op.alter_column('rnode', 'n_submitted', new_column_name='n_final')

    session = Session(bind=op.get_bind())
    assessments = session.query(Assessment).all()
    duration = None
    time_remaining = -1
    for i, assessment in enumerate(assessments):
        log_migration.info(
            "Assessment %d/%d T-%.1fs", i + 1, len(assessments), time_remaining)
        start = time.process_time()
        assessment.update_stats_descendants()
        end = time.process_time()
        if duration is None:
            duration = end - start
        else:
            duration = (duration * 0.8) + ((end - start) * 0.2)
        time_remaining = (len(assessments) - (i + 1)) * duration

    session.flush()

    op.alter_column('rnode', 'n_draft', nullable=False)


def downgrade():
    op.alter_column('rnode', 'n_final', new_column_name='n_submitted')
    op.drop_column('rnode', 'n_draft')


# What follows is a FROZEN copy of the model.

## response_type.py


from simpleeval import simple_eval, InvalidExpression


class ResponseTypeError(Exception):
    pass


class ExpressionError(ResponseTypeError):
    '''Error in response type definition'''
    pass


class ResponseError(ResponseTypeError):
    '''Error in user-provided response'''
    pass


class ResponseTypeCache:
    def __init__(self, rt_defs):
        self.rt_defs = rt_defs
        self.materialised_types = {}

    def __getitem__(self, id_):
        if id_ not in self.materialised_types:
            for rt_def in self.rt_defs:
                if rt_def['id'] == id_:
                    self.materialised_types[id_] = ResponseType(rt_def)
                    break
        return self.materialised_types[id_]


class ResponseType:
    def __init__(self, rt_def):
        self.id_ = rt_def['id']
        self.name = rt_def['name']
        self.parts = [ResponsePart(p_def) for p_def in rt_def['parts']]
        self.formula = rt_def.get('formula', None)

    def calculate_score(self, response):
        if response is None or len(response) != len(self.parts):
            raise ResponseError("Response is incomplete")

        score = 0.0
        variables = {}
        options = []

        # First pass: gather variables and calculate_score
        for i, (part_t, part) in enumerate(zip(self.parts, response)):
            try:
                part_index = part['index']
            except KeyError:
                raise ResponseError(
                    "Response is missing index for part %d" % (i + 1))

            try:
                if part_index < 0:
                    raise IndexError()
                option = part_t.options[part_index]
            except IndexError:
                raise ResponseError(
                    "Response part %d is out of range" % (i + 1))

            options.append(option)
            if part_t.id_ is not None:
                variables[part_t.id_] = option.score
                variables[part_t.id_ + '__i'] = part_index

            # Default is sum of all parts; may be overridden by custom formula
            score += option.score

        # Second pass: validate options according to predicates
        for i, option in enumerate(options):
            if option.predicate is not None:
                try:
                    enabled = simple_eval(option.predicate, names=variables)
                except InvalidExpression as e:
                    raise ExpressionError(str(e))
                if not bool(enabled):
                    raise ResponseError(
                        "Response part %d is invalid: conditions for option "
                        "'%s' are not met" % (i + 1, option.name))

        if self.formula is not None:
            try:
                score = simple_eval(self.formula, names=variables)
            except InvalidExpression as e:
                raise ExpressionError(str(e))

        return score

    def __repr__(self):
        return "ResponseType(%s)" % (self.name or self.id_)


class ResponsePart:
    def __init__(self, p_def):
        self.id_ = p_def.get('id', None)
        self.name = p_def.get('name', None)
        self.description = p_def.get('description', None)
        self.options = [ResponseOption(o_def)
                        for o_def in p_def['options']]

    def __repr__(self):
        return "ResponsePart(%s)" % (self.name or self.id_)


class ResponseOption:
    def __init__(self, o_def):
        self.score = o_def['score']
        self.name = o_def['name']
        self.predicate = o_def.get('if', None)

    def __repr__(self):
        return "ResponseOption(%s: %f)" % (self.name, self.score)


## model.py


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
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.orm import backref, foreign, relationship, remote, sessionmaker
from sqlalchemy.orm.session import object_session
from sqlalchemy.schema import CheckConstraint, ForeignKeyConstraint, \
    Index, MetaData, UniqueConstraint
from sqlalchemy.sql import func
from passlib.hash import sha256_crypt
from voluptuous import All, Any, Coerce, Length, Optional, Range, Required, \
    Schema

from old_deps.guid import GUID
from old_deps.history_meta import Versioned, versioned_session


log = logging.getLogger('app.model')
metadata = MetaData()
Base = declarative_base(metadata=metadata)


class ModelError(Exception):
    pass


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
        [program_id, survey_id, qnode_id, qnode_id, measure_id]
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
    human_name = Column(String, nullable=False)
    user_defined = Column(Boolean, nullable=False)
    value = Column(String)
    description = Column(String)

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


class Survey(Observable, Base):
    __tablename__ = 'survey'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    tracking_id = Column(GUID, default=uuid.uuid4, nullable=False)

    created = Column(DateTime, default=datetime.utcnow, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    # Survey is not editable after being finalised.
    finalised_date = Column(DateTime)
    title = Column(Text, nullable=False)
    description = Column(Text)
    _response_types = Column('response_types', JSON, nullable=False)

    @property
    def is_editable(self):
        return self.finalised_date is None

    _response_types_schema = Schema([
        {
            'id': All(str, Length(min=1)),
            'name': All(str, Length(min=1)),
            'parts': [
                {
                    Required('id', default=None): Any(
                        All(str, Length(min=1)), None),
                    Required('name', default=None): Any(
                        All(str, Length(min=1)), None),
                    Required('description', default=None): Any(
                        All(str, Length(min=1)), None),
                    'options': All([
                        {
                            'score': All(Coerce(float), Range(min=0, max=1)),
                            'name': All(str, Length(min=1)),
                            Required('if', default=None): Any(
                                All(str, Length(min=1)), None),
                            Required('description', default=None): Any(
                                All(str, Length(min=1)), None)
                        }
                    ], Length(min=2))
                }
            ],
            Required('formula', default=None): Any(
                All(str, Length(min=1)), None)
        }
    ], required=True)

    @property
    def response_types(self):
        return self._response_types

    @response_types.setter
    def response_types(self, rts):
        self._response_types = Survey._response_types_schema(rts)
        if hasattr(self, '_materialised_response_types'):
            del self._materialised_response_types

    @property
    def materialised_response_types(self):
        if not hasattr(self, '_materialised_response_types'):
            self._materialised_response_types = ResponseTypeCache(
                self._response_types)
        return self._materialised_response_types

    def update_stats_descendants(self):
        '''Updates the stats of an entire tree.'''
        for hierarchy in self.hierarchies:
            hierarchy.update_stats_descendants()

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
        Index('survey_tracking_id_index', tracking_id),
        Index('survey_created_index', created),
    )

    def __repr__(self):
        return "Survey(title={})".format(self.title)


class PurchasedSurvey(Base):
    __tablename__ = 'purchased_survey'
    survey_id = Column(GUID, nullable=False, primary_key=True)
    hierarchy_id = Column(GUID, nullable=False, primary_key=True)
    organisation_id = Column(GUID, nullable=False, primary_key=True)
    open_date = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ['hierarchy_id', 'survey_id'],
            ['hierarchy.id', 'hierarchy.survey_id']
        ),
        ForeignKeyConstraint(
            ['survey_id'],
            ['survey.id']
        ),
        ForeignKeyConstraint(
            ['organisation_id'],
            ['organisation.id']
        ),
    )

    organisation = relationship(Organisation, backref='purchased_surveys')
    hierarchy = relationship(
        'Hierarchy', backref=backref(
            'purchased_surveys', passive_deletes=True, order_by=open_date.desc()))

    # This constructor is used by association_proxy when adding items to the
    # collection.
    def __init__(self, hierarchy=None, organisation=None, **kwargs):
        self.hierarchy = hierarchy
        self.organisation = organisation
        super().__init__(**kwargs)


class Hierarchy(Observable, Base):
    __tablename__ = 'hierarchy'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(
        GUID, ForeignKey('survey.id'), nullable=False, primary_key=True)

    n_measures = Column(Integer, default=0, nullable=False)

    title = Column(Text, nullable=False)
    description = Column(Text)
    modified = Column(DateTime, nullable=True)
    deleted = Column(Boolean, default=False, nullable=False)

    _structure = Column('structure', JSON, nullable=False)

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

    @property
    def structure(self):
        return self._structure

    @structure.setter
    def structure(self, s):
        self._structure = Hierarchy._structure_schema(s)

    @property
    def ordered_measures(self):
        '''Returns all measures in depth-first order'''
        for qnode in self.qnodes:
            for measure in qnode.ordered_measures:
                yield measure

    def update_stats(self):
        '''Updates the stats this hierarchy.'''
        n_measures = sum(qnode.n_measures for qnode in self.qnodes)
        self.n_measures = n_measures
        self.modified = datetime.utcnow()

    def update_stats_descendants(self):
        '''Updates the stats of an entire subtree.'''
        for qnode in self.qnodes:
            qnode.update_stats_descendants()
        self.update_stats()

    @property
    def ob_type(self):
        return 'survey'

    @property
    def ob_ids(self):
        return [self.id, self.survey_id]

    @property
    def action_lineage(self):
        return [self.survey, self]

    def __repr__(self):
        return "Hierarchy(title={}, survey={})".format(
            self.title, getattr(self.survey, 'title', None))


Hierarchy.organisations = association_proxy('purchased_surveys', 'organisation')
Organisation.hierarchies = association_proxy('purchased_surveys', 'hierarchy')


class QuestionNode(Observable, Base):
    __tablename__ = 'qnode'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(GUID, nullable=False, primary_key=True)
    hierarchy_id = Column(GUID, nullable=False)
    parent_id = Column(GUID)

    deleted = Column(Boolean, default=False, nullable=False)
    seq = Column(Integer)
    n_measures = Column(Integer, default=0, nullable=False)
    total_weight = Column(Float, default=0, nullable=False)

    title = Column(Text, nullable=False)
    description = Column(Text)

    __table_args__ = (
        ForeignKeyConstraint(
            ['parent_id', 'survey_id'],
            ['qnode.id', 'qnode.survey_id']
        ),
        ForeignKeyConstraint(
            ['hierarchy_id', 'survey_id'],
            ['hierarchy.id', 'hierarchy.survey_id']
        ),
        ForeignKeyConstraint(
            ['survey_id'],
            ['survey.id']
        ),
        Index('qnode_parent_id_survey_id_index', parent_id, survey_id),
        Index('qnode_hierarchy_id_survey_id_index', hierarchy_id, survey_id),
    )

    survey = relationship(Survey)

    def get_rnode(self, assessment):
        if isinstance(assessment, (str, uuid.UUID)):
            assessment_id = assessment
        else:
            assessment_id = assessment.id
        return (object_session(self).query(ResponseNode)
            .filter_by(assessment_id=assessment_id, qnode_id=self.id)
            .first())

    def update_stats_ancestors(self):
        '''Updates the stats this node, and all ancestors.'''
        self.update_stats()
        if self.parent is not None:
            self.parent.update_stats_ancestors()
        else:
            self.hierarchy.update_stats()

    def update_stats_descendants(self):
        '''Updates the stats of an entire subtree.'''
        for child in self.children:
            child.update_stats_descendants()
        self.update_stats()

    def update_stats(self):
        total_weight = sum(measure.weight for measure in self.measures)
        total_weight += sum(child.total_weight for child in self.children)
        n_measures = len(self.measures)
        n_measures += sum(child.n_measures for child in self.children)

        self.total_weight = total_weight
        self.n_measures = n_measures

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
    def ordered_measures(self):
        '''Returns all measures in depth-first order'''
        for child in self.children:
            for measure in child.ordered_measures:
                yield measure
        for measure in self.measures:
            yield measure

    @property
    def ob_type(self):
        return 'qnode'

    @property
    def ob_ids(self):
        return [self.id, self.survey_id]

    @property
    def action_lineage(self):
        return [self.survey, self.hierarchy] + self.lineage()

    def __repr__(self):
        return "QuestionNode(title={}, survey={})".format(
            self.title, getattr(self.survey, 'title', None))


class Measure(Observable, Base):
    __tablename__ = 'measure'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(
        GUID, ForeignKey("survey.id"), nullable=False, primary_key=True)
    deleted = Column(Boolean, default=False, nullable=False)

    title = Column(Text, nullable=False)
    weight = Column(Float, nullable=False)
    intent = Column(Text, nullable=True)
    inputs = Column(Text, nullable=True)
    scenario = Column(Text, nullable=True)
    questions = Column(Text, nullable=True)
    response_type = Column(Text, nullable=False)

    survey = relationship(
        Survey, backref=backref('measures', passive_deletes=True))

    def get_parent(self, hierarchy):
        if isinstance(hierarchy, (str, uuid.UUID)):
            hierarchy_id = hierarchy
        else:
            hierarchy_id = hierarchy.id
        for p in self.parents:
            if str(p.hierarchy_id) == str(hierarchy_id):
                return p
        return None

    def get_qnode_measure(self, hierarchy):
        if isinstance(hierarchy, (str, uuid.UUID)):
            hierarchy_id = hierarchy
        else:
            hierarchy_id = hierarchy.id
        for qm in self.qnode_measures:
            if str(qm.qnode.hierarchy_id) == str(hierarchy_id):
                return qm
        return None

    def get_seq(self, hierarchy):
        qm = self.get_qnode_measure(hierarchy)
        if qm:
            return qm.seq
        return None

    def get_path(self, hierarchy):
        qm = self.get_qnode_measure(hierarchy)
        if qm:
            return qm.get_path()
        return None

    def get_response(self, assessment):
        if isinstance(assessment, str):
            assessment_id = assessment
        else:
            assessment_id = assessment.id
        return (object_session(self).query(Response)
            .filter_by(assessment_id=assessment_id, measure_id=self.id)
            .first())

    def lineage(self, hierarchy=None):
        if hierarchy is None:
            hierarchy_id = None
        elif isinstance(hierarchy, (str, uuid.UUID)):
            hierarchy_id = hierarchy
        else:
            hierarchy_id = hierarchy.id

        if hierarchy_id:
            qms = [qm for qm in self.qnode_measures
                   if str(qm.hierarchy_id) == str(hierarchy_id)]
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
        return [self.id, self.survey_id]

    @property
    def action_lineage(self):
        hs = [p.hierarchy for p in self.parents]
        return [self.survey] + hs + self.lineage()

    def __repr__(self):
        return "Measure(title={}, survey={})".format(
            self.title, getattr(self.survey, 'title', None))


class QnodeMeasure(Base):
    # This is an association object for qnodes <-> measures. Normally this would
    # be done with a raw table, but because we want access to the `seq` column,
    # it needs to be a mapped class.
    __tablename__ = 'qnode_measure_link'
    survey_id = Column(GUID, nullable=False, primary_key=True)
    qnode_id = Column(GUID, nullable=False, primary_key=True)
    measure_id = Column(GUID, nullable=False, primary_key=True)

    seq = Column(Integer)

    __table_args__ = (
        ForeignKeyConstraint(
            ['qnode_id', 'survey_id'],
            ['qnode.id', 'qnode.survey_id']
        ),
        ForeignKeyConstraint(
            ['measure_id', 'survey_id'],
            ['measure.id', 'measure.survey_id']
        ),
        ForeignKeyConstraint(
            ['survey_id'],
            ['survey.id']
        ),
        Index('qnodemeasure_qnode_id_survey_id_index', qnode_id, survey_id),
        Index('qnodemeasure_measure_id_survey_id_index', measure_id, survey_id),
    )

    survey = relationship(Survey)

    # This constructor is used by association_proxy when adding items to the
    # collection.
    def __init__(self, measure=None, qnode=None, seq=None, survey=None,
                 **kwargs):
        self.measure = measure
        self.qnode = qnode
        self.seq = seq

        # Accessing measure.survey or qnode.survey may cause a flush if it
        # hasn't been initialised yet - but we don't want that to happen now,
        # because this object hasn't been fully initialised, which would mean
        # the insertion would fail and cause a rollback. Instead, fall back to
        # assigning the survey ID instead of using the relationship.
        with object_session(self).no_autoflush:
            if survey:
                self.survey = survey
            elif measure:
                self.survey = measure.survey
                if not self.survey:
                    self.survey_id = measure.survey_id
            elif qnode:
                self.survey = qnode.survey
                if not self.survey:
                    self.survey_id = qnode.survey_id

        super().__init__(**kwargs)

    def get_path(self):
        return "%s %d." % (self.qnode.get_path(), self.seq + 1)

    def __repr__(self):
        return "QnodeMeasure(qnode={}, measure={}, survey={})".format(
            getattr(self.qnode, 'title', None),
            getattr(self.measure, 'title', None),
            getattr(self.survey, 'title', None))


class Assessment(Observable, Base):
    __tablename__ = 'assessment'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(GUID, nullable=False)
    organisation_id = Column(GUID, nullable=False)
    hierarchy_id = Column(GUID, nullable=False)

    title = Column(Text)
    approval = Column(
        Enum('draft', 'final', 'reviewed', 'approved', native_enum=False),
        nullable=False)
    created = Column(DateTime, default=datetime.utcnow, nullable=False)
    modified = Column(DateTime, nullable=True)
    deleted = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ['hierarchy_id', 'survey_id'],
            ['hierarchy.id', 'hierarchy.survey_id']
        ),
        ForeignKeyConstraint(
            ['survey_id'],
            ['survey.id']
        ),
        ForeignKeyConstraint(
            ['organisation_id'],
            ['organisation.id']
        ),
        Index('assessment_organisation_id_hierarchy_id_index',
              organisation_id, hierarchy_id),
    )

    survey = relationship(Survey)
    organisation = relationship(Organisation)

    @property
    def ordered_responses(self):
        '''Returns all responses in depth-first order'''
        for rnode in self.rnodes:
            for response in rnode.ordered_responses:
                yield response

    @property
    def rnodes(self):
        for qnode in self.hierarchy.qnodes:
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

    def update_stats_descendants(self):
        for qnode in self.hierarchy.qnodes:
            rnode = qnode.get_rnode(self)
            if rnode is None:
                rnode = ResponseNode(
                    survey=self.survey,
                    assessment=self,
                    qnode=qnode)
                object_session(self).add(rnode)
                object_session(self).flush()
            rnode.update_stats_descendants()

    def __repr__(self):
        return "Assessment(survey={}, org={})".format(
            getattr(self.survey, 'title', None),
            getattr(self.organisation, 'name', None))


class ResponseNode(Observable, Base):
    __tablename__ = 'rnode'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(GUID, nullable=False)
    assessment_id = Column(GUID, nullable=False)
    qnode_id = Column(GUID, nullable=False)

    n_draft = Column(Integer, default=0, nullable=False)
    n_final = Column(Integer, default=0, nullable=False)
    n_reviewed = Column(Integer, default=0, nullable=False)
    n_approved = Column(Integer, default=0, nullable=False)
    score = Column(Float, default=0.0, nullable=False)

    n_not_relevant = Column(Integer, default=0, nullable=False)
    not_relevant = Column(Boolean, default=False, nullable=False)

    importance = Column(Float)
    urgency = Column(Float)
    max_importance = Column(Float, default=0.0, nullable=False)
    max_urgency = Column(Float, default=0.0, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ['qnode_id', 'survey_id'],
            ['qnode.id', 'qnode.survey_id']
        ),
        ForeignKeyConstraint(
            ['survey_id'],
            ['survey.id']
        ),
        ForeignKeyConstraint(
            ['assessment_id'],
            ['assessment.id']
        ),
        UniqueConstraint('qnode_id', 'assessment_id'),
        Index('rnode_qnode_id_assessment_id_index', qnode_id, assessment_id),
    )

    survey = relationship(Survey)
    assessment = relationship(Assessment)

    @property
    def parent(self):
        if self.qnode.parent is None:
            return None
        return self.qnode.parent.get_rnode(self.assessment)

    @property
    def children(self):
        for child_qnode in self.qnode.children:
            rnode = child_qnode.get_rnode(self.assessment)
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
        for measure in self.qnode.measures:
            response = measure.get_response(self.assessment)
            if response is not None:
                yield response

    def lineage(self):
        return [q.get_rnode(self.assessment_id) for q in self.qnode.lineage()]

    @property
    def ob_type(self):
        return 'rnode'

    @property
    def ob_title(self):
        return self.qnode.title

    @property
    def ob_ids(self):
        return [self.qnode_id, self.assessment_id]

    @property
    def action_lineage(self):
        # It would be nice to include the program and survey in this list, but
        # then everyone who was subscribed to a survey would get spammed with
        # all the submissions against it.
        return [self.assessment.organisation, self.assessment] + self.lineage()

    @property
    def action_descriptor(self):
        # Use qnodes instead of rnodes for lineage, because rnode.id is not part
        # of the API.
        lineage = ([self.assessment.id] +
                   [q.id for q in self.qnode.lineage()])
        return ActionDescriptor(
            self.ob_title, self.ob_type, self.ob_ids, lineage)

    def update_stats(self):
        if self.not_relevant:
            self.score = 0.0
            self.n_approved = self.qnode.n_measures
            self.n_reviewed = self.qnode.n_measures
            self.n_final = self.qnode.n_measures
            self.n_draft = self.qnode.n_measures
            self.n_not_relevant = self.qnode.n_measures
            self.max_importance = 0.0
            self.max_urgency = 0.0
            return

        score = 0.0
        n_approved = 0
        n_reviewed = 0
        n_final = 0
        n_draft = 0
        n_not_relevant = 0
        max_importance = 0.0
        max_urgency = 0.0

        for c in self.children:
            score += c.score
            n_approved += c.n_approved
            n_reviewed += c.n_reviewed
            n_final += c.n_final
            n_draft += c.n_draft
            n_not_relevant += c.n_not_relevant
            max_importance = max(max_importance, c.max_importance or 0.0)
            max_urgency = max(max_urgency, c.max_urgency or 0.0)

        for r in self.responses:
            score += r.score
            if r.approval in {'draft', 'final', 'reviewed', 'approved'}:
                n_draft += 1
            if r.approval in {'final', 'reviewed', 'approved'}:
                n_final += 1
            if r.approval in {'reviewed', 'approved'}:
                n_reviewed += 1
            if r.approval in {'approved'}:
                n_approved += 1
            if r.not_relevant:
                n_not_relevant += 1

        self.score = score
        self.n_approved = n_approved
        self.n_reviewed = n_reviewed
        self.n_final = n_final
        self.n_draft = n_draft
        self.n_not_relevant = n_not_relevant
        self.max_importance = self.importance or max_importance
        self.max_urgency = self.urgency or max_urgency

    def update_stats_descendants(self):
        for qchild in self.qnode.children:
            rchild = qchild.get_rnode(self.assessment)
            if rchild is None:
                rchild = ResponseNode(
                    survey=self.survey,
                    assessment=self.assessment,
                    qnode=qchild)
                object_session(self).add(rchild)
                object_session(self).flush()
            rchild.update_stats_descendants()
        for response in self.responses:
            response.update_stats()
        self.update_stats()

    def update_stats_ancestors(self):
        self.update_stats()
        parent = self.parent
        if parent is None:
            qnode = self.qnode.parent
            if qnode is None:
                return
            parent = ResponseNode(
                survey=self.survey, assessment=self.assessment, qnode=qnode)
            object_session(self).add(parent)
            object_session(self).flush()
        parent.update_stats_ancestors()

    def __repr__(self):
        org = getattr(self.assessment, 'organisation', None)
        return "ResponseNode(qnode={}, survey={}, org={})".format(
            getattr(self.qnode, 'title', None),
            getattr(self.survey, 'title', None),
            getattr(org, 'name', None))


class Response(Observable, Versioned, Base):
    __tablename__ = 'response'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(GUID, nullable=False)
    measure_id = Column(GUID, nullable=False)
    assessment_id = Column(GUID, nullable=False)
    user_id = Column(GUID, nullable=False)

    comment = Column(Text, nullable=False)
    not_relevant = Column(Boolean, nullable=False)
    _response_parts = Column('response_parts', JSON, nullable=False)
    audit_reason = Column(Text)
    modified = Column(DateTime, nullable=False)

    score = Column(Float, default=0.0, nullable=False)
    approval = Column(
        Enum('draft', 'final', 'reviewed', 'approved', native_enum=False),
        nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ['measure_id', 'survey_id'],
            ['measure.id', 'measure.survey_id'],
            info={'version': True}
        ),
        ForeignKeyConstraint(
            ['survey_id'],
            ['survey.id'],
            info={'version': True}
        ),
        ForeignKeyConstraint(
            ['user_id'],
            ['appuser.id'],
            info={'version': True}
        ),
        ForeignKeyConstraint(
            ['assessment_id'],
            ['assessment.id'],
            info={'version': True}
        ),
        UniqueConstraint('measure_id', 'assessment_id'),
        Index('response_assessment_id_measure_id_index',
              assessment_id, measure_id),
    )

    survey = relationship(Survey)
    user = relationship(AppUser)

    @property
    def parent_qnode(self):
        for p in self.measure.parents:
            if p.hierarchy_id == self.assessment.hierarchy_id:
                return p
        # Might happen if a measure is unlinked after the response is
        # created
        return None

    @property
    def parent(self):
        qnode = self.parent_qnode
        if qnode is None:
            # Might happen if a measure is unlinked after the response is
            # created
            return None
        return qnode.get_rnode(self.assessment)

    _response_parts_schema = Schema([
        {
            'index': int,
            'note': All(str, Length(min=1))
        }
    ], required=True)

    @property
    def response_parts(self):
        return self._response_parts

    @response_parts.setter
    def response_parts(self, s):
        self._response_parts = Response._response_parts_schema(s)

    def lineage(self):
        return ([q.get_rnode(self.assessment_id)
                 for q in self.parent_qnode.lineage()] +
                [self])

    @property
    def ob_type(self):
        return 'response'

    @property
    def ob_title(self):
        return self.measure.title

    @property
    def ob_ids(self):
        return [self.measure_id, self.assessment_id]

    @property
    def action_lineage(self):
        # It would be nice to include the program and survey in this list, but
        # then everyone who was subscribed to a survey would get spammed with
        # all the submissions against it.
        return [self.assessment.organisation, self.assessment] + self.lineage()

    @property
    def action_descriptor(self):
        # Use qnodes and the measure instead of rnodes and the response for
        # lineage, because rnode.id and response.id are not part of the API.
        lineage = ([self.assessment.id] +
                   [q.id for q in self.parent_qnode.lineage()] +
                   [self.measure_id])
        return ActionDescriptor(
            self.ob_title, self.ob_type, self.ob_ids, lineage)

    def update_stats(self):
        if self.not_relevant:
            score = 0.0
        else:
            try:
                rt = self.survey.materialised_response_types[
                    self.measure.response_type]
            except KeyError:
                raise ModelError(
                    "Measure '%s': response type is not defined." %
                    self.measure.title)
            try:
                score = rt.calculate_score(self.response_parts)
            except ResponseError as e:
                raise ModelError(
                    "Could not calculate score for response %s %s: %s" %
                    (self.measure.get_path(self.assessment.hierarchy),
                     self.measure.title, str(e)))
        self.score = score * self.measure.weight

    def update_stats_ancestors(self):
        self.update_stats()
        parent = self.parent
        if parent is None:
            qnode = self.parent_qnode
            if qnode is None:
                return
            parent = ResponseNode(
                survey=self.survey, assessment=self.assessment, qnode=qnode)
            object_session(self).add(parent)
        object_session(self).flush()
        parent.update_stats_ancestors()

    def __repr__(self):
        org = getattr(self.assessment, 'organisation', None)
        return "Response(measure={}, survey={}, org={})".format(
            getattr(self.measure, 'title', None),
            getattr(self.survey, 'title', None),
            getattr(org, 'name', None))



# Lists and Complex Relationships
#
# We need to give explicit join rules due to use of foreign key in composite
# primary keys. The foreign_keys argument is used to mark which columns are
# writable. For example, where a class has a survey relationship that can write
# to the survey_id column, the foreign_keys list for other relationships will
# not include the survey_id column so that there is no ambiguity when both
# relationships are written to.
# http://docs.sqlalchemy.org/en/rel_1_0/orm/join_conditions.html#overlapping-foreign-keys
#
# Addtitionally, self-referential relationships (trees) need the remote_side
# argument.
# http://docs.sqlalchemy.org/en/rel_1_0/orm/self_referential.html#composite-adjacency-lists


# Use verbose back_populates instead of backref because the relationships are
# asymmetric: a deleted hierarchy still has a survey, but a survey has no
# deleted hierarchies.
#
# http://docs.sqlalchemy.org/en/latest/orm/backref.html#one-way-backrefs
#
# It is therefore possible to create an inconsistent in-memory model:
#
#     s = Survey(title="Program 1")
#     h = Hierarchy(title="Survey 1", deleted=True)
#     s.hierarchies.append(h)
#     print(s.hierarchies)
#     # prints [Hierarchy(title=Survey 1, survey=Program 1)]
#
# After calling `session.flush()`, the list of hierarchies will be empty.
# Maintaining consistency is the responsibility of the programmer. In this
# example, the programmer should have either:
#
#  - Not set `h.deleted = True`, to avoid violating the join condition.
#  - Used `h.survey = s`, which does not back-populate `Survey.hierarchies`.
#
# When soft-deleting an entry, the programmer should:
#
#  1. Set `h.deleted = True`.
#  2. Remove it from the collection with `s.hierarchies.remove(h)`.
#  3. Reinstate the link to the owning program with `h.survey = s`.


AppUser.organisation = relationship(Organisation)

Organisation.users = relationship(
    AppUser, back_populates="organisation", passive_deletes=True,
    primaryjoin=(Organisation.id == AppUser.organisation_id) &
                (AppUser.deleted == False))


Hierarchy.survey = relationship(Survey)

Survey.hierarchies = relationship(
    Hierarchy, back_populates="survey", passive_deletes=True,
    order_by='Hierarchy.title',
    primaryjoin=(Survey.id == Hierarchy.survey_id) &
                (Hierarchy.deleted == False))


# The link from a node to a hierarchy uses a one-way backref for another reason.
# We don't want modifications to this attribute to affect the other side of the
# relationship: otherwise non-root nodes couldn't have their hierarchies set
# easily.
# http://docs.sqlalchemy.org/en/latest/orm/backref.html#one-way-backrefs
QuestionNode.hierarchy = relationship(
    Hierarchy,
    primaryjoin=(foreign(QuestionNode.hierarchy_id) == remote(Hierarchy.id)) &
                (QuestionNode.survey_id == remote(Hierarchy.survey_id)))


# "Children" of the hierarchy: these are roots of the qnode tree. Use
# back_populates instead of backref for the reasons described above.
Hierarchy.qnodes = relationship(
    QuestionNode, back_populates='hierarchy', passive_deletes=True,
    order_by=QuestionNode.seq, collection_class=ordering_list('seq'),
    primaryjoin=(foreign(QuestionNode.hierarchy_id) == Hierarchy.id) &
                (QuestionNode.survey_id == Hierarchy.survey_id) &
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
                (QuestionNode.survey_id == remote(QuestionNode.survey_id)))


QuestionNode.children = relationship(
    QuestionNode, back_populates='parent', passive_deletes=True,
    order_by=QuestionNode.seq, collection_class=ordering_list('seq'),
    primaryjoin=(foreign(remote(QuestionNode.parent_id)) == QuestionNode.id) &
                (remote(QuestionNode.survey_id) == QuestionNode.survey_id) &
                (remote(QuestionNode.deleted) == False))


QuestionNode.qnode_measures = relationship(
    QnodeMeasure, backref='qnode', cascade='all, delete-orphan',
    order_by=QnodeMeasure.seq, collection_class=ordering_list('seq'),
    primaryjoin=(foreign(QnodeMeasure.qnode_id) == QuestionNode.id) &
                (QnodeMeasure.survey_id == QuestionNode.survey_id))


Measure.qnode_measures = relationship(
    QnodeMeasure, backref='measure',
    primaryjoin=(foreign(QnodeMeasure.measure_id) == Measure.id) &
                (QnodeMeasure.survey_id == Measure.survey_id))


QuestionNode.measures = association_proxy('qnode_measures', 'measure')
QuestionNode.measure_seq = association_proxy('qnode_measures', 'seq')
Measure.parents = association_proxy('qnode_measures', 'qnode')


Assessment.hierarchy = relationship(
    Hierarchy,
    primaryjoin=(foreign(Assessment.hierarchy_id) == Hierarchy.id) &
                (Assessment.survey_id == Hierarchy.survey_id))


Assessment.responses = relationship(
    Response, backref='assessment', passive_deletes=True)


ResponseNode.qnode = relationship(
    QuestionNode,
    primaryjoin=(foreign(ResponseNode.qnode_id) == QuestionNode.id) &
                (ResponseNode.survey_id == QuestionNode.survey_id))


Response.measure = relationship(
    Measure,
    primaryjoin=(foreign(Response.measure_id) == Measure.id) &
                (Response.survey_id == Measure.survey_id))
