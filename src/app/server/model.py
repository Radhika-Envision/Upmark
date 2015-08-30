from contextlib import contextmanager
from datetime import datetime
import os
import sys
import uuid

from sqlalchemy import Boolean, create_engine, Column, DateTime, Enum, Float, \
    ForeignKey, Index, Integer, String, Text, Table, LargeBinary
from sqlalchemy.dialects.postgresql import JSON
import sqlalchemy.exc
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.orm import backref, foreign, relationship, remote, sessionmaker
from sqlalchemy.orm.session import object_session
from sqlalchemy.schema import UniqueConstraint, ForeignKeyConstraint, Index,\
    MetaData
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import and_
from passlib.hash import sha256_crypt
from voluptuous import All, Any, Coerce, Length, Optional, Range, Required, \
    Schema

from guid import GUID
from history_meta import Versioned, versioned_session
from response_type import ResponseTypeCache


metadata = MetaData()
Base = declarative_base(metadata=metadata)


class ModelError(Exception):
    pass


class SystemConfig(Base):
    __tablename__ = 'systemconfig'
    name = Column(String, primary_key=True, nullable=False)
    human_name = Column(String, nullable=False)
    user_defined = Column(Boolean, nullable=False)
    value = Column(String)
    description = Column(String)

    def __repr__(self):
        return "SystemConfig(name={}, value={})".format(self.name, self.value)


class Organisation(Base):
    __tablename__ = 'organisation'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)

    name = Column(Text, nullable=False)
    url = Column(Text, nullable=True)
    region = Column(Text, nullable=False)
    number_of_customers = Column(Integer, nullable=False)
    created = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('organisation_name_key', func.lower(name), unique=True),
    )

    def __repr__(self):
        return "Organisation(name={})".format(self.name)


class AppUser(Base):
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
    enabled = Column(Boolean, nullable=False, default=True)

    def set_password(self, plaintext):
        self.password = sha256_crypt.encrypt(plaintext)

    def check_password(self, plaintext):
        return sha256_crypt.verify(plaintext, self.password)

    __table_args__ = (
        Index('appuser_email_key', func.lower(email), unique=True),
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


class Survey(Base):
    __tablename__ = 'survey'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    tracking_id = Column(GUID, default=uuid.uuid4, nullable=False)

    created = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Survey is not editable after being finalised.
    finalised_date = Column(DateTime)
    # Survey is not open for responses until after the open_date.
    open_date = Column(DateTime)
    title = Column(Text, nullable=False)
    description = Column(Text)
    _response_types = Column('response_types', JSON, nullable=False)

    @property
    def is_editable(self):
        return self.finalised_date is None

    @property
    def is_open(self):
        return self.open_date is not None

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
                    'options': All([
                        {
                            'score': All(Coerce(float), Range(min=0, max=1)),
                            'name': All(str, Length(min=1)),
                            Required('if', default=None): Any(
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

    def __repr__(self):
        return "Survey(title={})".format(self.title)


class Hierarchy(Base):
    __tablename__ = 'hierarchy'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(
        GUID, ForeignKey('survey.id'), nullable=False, primary_key=True)

    n_measures = Column(Integer, default=0, nullable=False)

    title = Column(Text, nullable=False)
    description = Column(Text)
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

    def update_stats(self):
        '''Updates the stats this hierarchy.'''
        n_measures = sum(qnode.n_measures for qnode in self.qnodes)
        self.n_measures = n_measures

    def update_stats_descendants(self):
        '''Updates the stats of an entire subtree.'''
        for qnode in self.qnodes:
            qnode.update_stats_descendants()
        self.update_stats()

    def __repr__(self):
        return "Hierarchy(title={}, survey={})".format(
            self.title, getattr(self.survey, 'title', None))


class QuestionNode(Base):
    __tablename__ = 'qnode'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(GUID, nullable=False, primary_key=True)
    hierarchy_id = Column(GUID, nullable=False)
    parent_id = Column(GUID)

    seq = Column(Integer)
    n_measures = Column(Integer, default=0, nullable=False)

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
    )

    survey = relationship(Survey)

    def get_rnode(self, assessment):
        if isinstance(assessment, str):
            assessment_id = assessment
        else:
            assessment_id = assessment.id
        return (object_session(self).query(ResponseNode)
            .filter_by(assessment_id=assessment_id, qnode_id=self.id)
            .first())

    def update_stats_ancestors(self):
        '''Updates the stats this node, and all ancestors.'''
        n_measures = len(self.measures)
        n_measures += sum(child.n_measures for child in self.children)
        self.n_measures = n_measures
        if self.parent is not None:
            self.parent.update_stats_ancestors()
        else:
            self.hierarchy.update_stats()

    def update_stats_descendants(self):
        '''Updates the stats of an entire subtree.'''
        for child in self.children:
            child.update_stats_descendants()
        n_measures = len(self.measures)
        n_measures += sum(child.n_measures for child in self.children)
        self.n_measures = n_measures

    def __repr__(self):
        return "QuestionNode(title={}, survey={})".format(
            self.title, getattr(self.survey, 'title', None))


class Measure(Base):
    __tablename__ = 'measure'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(
        GUID, ForeignKey("survey.id"), nullable=False, primary_key=True)

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
            if p.hierarchy_id == hierarchy_id:
                return p
        return None

    def get_response(self, assessment):
        if isinstance(assessment, str):
            assessment_id = assessment
        else:
            assessment_id = assessment.id
        return (object_session(self).query(Response)
            .filter_by(assessment_id=assessment_id, measure_id=self.id)
            .first())

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
    )

    survey = relationship(Survey)

    # This constructor is used by association_proxy when adding items to the
    # colleciton.
    def __init__(self, measure=None, qnode=None, seq=None, survey=None,
                 **kwargs):
        self.measure = measure
        self.qnode = qnode
        self.seq = seq
        if survey is not None:
            self.survey_id = survey.id
        elif measure is not None:
            self.survey_id = measure.survey_id
        elif qnode is not None:
            self.survey_id = qnode.survey_id
        super().__init__(**kwargs)

    def __repr__(self):
        return "QnodeMeasure(qnode={}, measure={}, survey={})".format(
            getattr(self.qnode, 'title', None),
            getattr(self.measure, 'title', None),
            getattr(self.survey, 'title', None))


class Assessment(Base):
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


class ResponseNode(Base):
    __tablename__ = 'rnode'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(GUID, nullable=False)
    assessment_id = Column(GUID, nullable=False)
    qnode_id = Column(GUID, nullable=False)

    n_submitted = Column(Integer, default=0, nullable=False)
    n_reviewed = Column(Integer, default=0, nullable=False)
    n_approved = Column(Integer, default=0, nullable=False)
    score = Column(Float, default=0.0, nullable=False)

    n_not_relevant = Column(Integer, default=0, nullable=False)
    not_relevant = Column(Boolean, default=False, nullable=False)

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

    def update_stats(self):
        if self.not_relevant:
            self.score = 0.0
            self.n_approved = self.qnode.n_measures
            self.n_reviewed = self.qnode.n_measures
            self.n_submitted = self.qnode.n_measures
            self.n_not_relevant = self.qnode.n_measures
            return

        score = 0.0
        n_approved = 0
        n_reviewed = 0
        n_submitted = 0
        n_not_relevant = 0

        for c in self.children:
            score += c.score
            n_approved += c.n_approved
            n_reviewed += c.n_reviewed
            n_submitted += c.n_submitted
            n_not_relevant += c.n_not_relevant

        for r in self.responses:
            score += r.score
            if r.approval in {'final', 'reviewed', 'approved'}:
                n_submitted += 1
            if r.approval in {'reviewed', 'approved'}:
                n_reviewed += 1
            if r.approval in {'approved'}:
                n_approved += 1
            if r.not_relevant:
                n_not_relevant += 1

        self.score = score
        self.n_approved = n_approved
        self.n_reviewed = n_reviewed
        self.n_submitted = n_submitted
        self.n_not_relevant = n_not_relevant

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


class Response(Versioned, Base):
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
            ['measure.id', 'measure.survey_id']
        ),
        ForeignKeyConstraint(
            ['survey_id'],
            ['survey.id']
        ),
        ForeignKeyConstraint(
            ['user_id'],
            ['appuser.id']
        ),
        ForeignKeyConstraint(
            ['assessment_id'],
            ['assessment.id']
        ),
        UniqueConstraint('measure_id', 'assessment_id'),
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
            score = rt.calculate_score(self.response_parts)
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


class Attachment(Base):
    __tablename__ = 'attachment'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    organisation_id = Column(
        GUID, ForeignKey("organisation.id"), nullable=False)
    response_id = Column(GUID, ForeignKey("response.id"), nullable=False)

    storage = Column(
        Enum('external', 'aws', 'database', native_enum=False),
        nullable=False)
    file_name = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
    blob = Column(LargeBinary, nullable=True)

    response = relationship(Response, backref='attachments')
    organisation = relationship(Organisation)


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


Organisation.users = relationship(
    AppUser, backref="organisation", passive_deletes=True)


Survey.hierarchies = relationship(
    Hierarchy, backref="survey", passive_deletes=True,
    order_by='Hierarchy.title')


# The link from a node to a hierarchy uses a one-way backref. Although this is
# kind of the backref of Hierarchy.qnodes (below), we don't want modifications
# to this attribute to affect the other side of the relationship: otherwise non-
# root nodes couldn't have their hierarchies set easily.
# http://docs.sqlalchemy.org/en/latest/orm/backref.html#one-way-backrefs
QuestionNode.hierarchy = relationship(
    Hierarchy,
    primaryjoin=and_(foreign(QuestionNode.hierarchy_id) == remote(Hierarchy.id),
                     QuestionNode.survey_id == remote(Hierarchy.survey_id)))


# "Children" of the hierarchy: these are roots of the qnode tree. Use
# back_populates instead of backref for the reasons described above.
Hierarchy.qnodes = relationship(
    QuestionNode, back_populates='hierarchy', passive_deletes=True,
    order_by=QuestionNode.seq, collection_class=ordering_list('seq'),
    primaryjoin=and_(and_(foreign(QuestionNode.hierarchy_id) == Hierarchy.id,
                          QuestionNode.survey_id == Hierarchy.survey_id),
                     QuestionNode.parent_id == None))


# The remote_side argument needs to be set on the many-to-one side, so it's
# easier to define this relationship from the perspective of the child, i.e.
# as QuestionNode.parent instead of QuestionNode.children. The backref still
# works. The collection arguments (passive_deletes, order_by, etc) need to be
# placed on the one-to-many side, so they are nested in the backref argument.
QuestionNode.parent = relationship(
    QuestionNode, backref=backref(
        'children', passive_deletes=True,
        order_by=QuestionNode.seq, collection_class=ordering_list('seq')),
    primaryjoin=and_(foreign(QuestionNode.parent_id) == remote(QuestionNode.id),
                     QuestionNode.survey_id == remote(QuestionNode.survey_id)))


QuestionNode.qnode_measures = relationship(
    QnodeMeasure, backref='qnode', cascade='all, delete-orphan',
    order_by=QnodeMeasure.seq, collection_class=ordering_list('seq'),
    primaryjoin=and_(foreign(QnodeMeasure.qnode_id) == QuestionNode.id,
                     QnodeMeasure.survey_id == QuestionNode.survey_id))


Measure.qnode_measures = relationship(
    QnodeMeasure, backref='measure',
    primaryjoin=and_(foreign(QnodeMeasure.measure_id) == Measure.id,
                     QnodeMeasure.survey_id == Measure.survey_id))


QuestionNode.measures = association_proxy('qnode_measures', 'measure')
QuestionNode.measure_seq = association_proxy('qnode_measures', 'seq')
Measure.parents = association_proxy('qnode_measures', 'qnode')


Assessment.hierarchy = relationship(
    Hierarchy,
    primaryjoin=and_(foreign(Assessment.hierarchy_id) == Hierarchy.id,
                     Assessment.survey_id == Hierarchy.survey_id))


Assessment.responses = relationship(
    Response, backref='assessment', passive_deletes=True)


ResponseNode.qnode = relationship(
    QuestionNode,
    primaryjoin=and_(foreign(ResponseNode.qnode_id) == QuestionNode.id,
                     ResponseNode.survey_id == QuestionNode.survey_id))


Response.measure = relationship(
    Measure,
    primaryjoin=and_(foreign(Response.measure_id) == Measure.id,
                     Response.survey_id == Measure.survey_id))


Session = None
VersionedSession = None


@contextmanager
def session_scope(version=False):
    # http://docs.sqlalchemy.org/en/latest/orm/session_basics.html#when-do-i-construct-a-session-when-do-i-commit-it-and-when-do-i-close-it
    """Provide a transactional scope around a series of operations."""
    if version:
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


def connect_db(url):
    global Session, VersionedSession
    engine = create_engine(url)
    conn = engine.connect()
    # Never drop the schema here.
    # - For short-term testing, use psql.
    # - For breaking changes, add migration code to the alembic scripts.
    Session = sessionmaker(bind=engine)
    VersionedSession = sessionmaker(bind=engine)
    versioned_session(VersionedSession)
    return engine


def initialise_schema(engine):
    Base.metadata.create_all(engine)
