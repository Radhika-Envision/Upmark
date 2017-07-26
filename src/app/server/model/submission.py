__all__ = [
    'Attachment',
    'Response',
    'ResponseHistory',
    'ResponseNode',
    'Submission',
]

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, \
    ForeignKey, Index, Integer, Text, LargeBinary
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import foreign, relationship, validates
from sqlalchemy.orm.session import object_session
from sqlalchemy.schema import ForeignKeyConstraint
from voluptuous.humanize import validate_with_humanized_errors

import response_type
from .observe import ActionDescriptor, Observable
from .base import Base, to_id
from .guid import GUID
from .history_meta import Versioned
from .survey import Program, QnodeMeasure, QuestionNode, Survey
from .user import AppUser, Organisation


class Submission(Observable, Base):
    __tablename__ = 'submission'
    id = Column(GUID, default=GUID.gen, primary_key=True)
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
    def surveygroups(self):
        return self.program.surveygroups & self.organisation.surveygroups

    @property
    def ordered_responses(self):
        '''Returns all responses in depth-first order'''
        for qnode_measure in self.survey.ordered_qnode_measures:
            response = Response.from_measure(qnode_measure, self)
            if response is not None:
                yield response

    @property
    def rnodes(self):
        for qnode in self.survey.qnodes:
            rnode = ResponseNode.from_qnode(qnode, self)
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
        Index('rnode_qnode_id_submission_id_index', qnode_id, submission_id),
    )

    program = relationship(Program)
    submission = relationship(Submission)

    @classmethod
    def from_qnode(cls, qnode, submission, create=False):
        session = object_session(qnode)
        sid = to_id(submission)
        rnode = session.query(cls).get((sid, qnode.id))
        if not rnode and create:
            rnode = cls(program=qnode.program, qnode=qnode)
            rnode.submission_id = sid
            session.add(rnode)
            # Without this flush, rnode.responses may be incomplete. Test with
            # test_daemon.DaemonTest.
            # TODO: Perahps this could be avoided if the recalculation was done
            # in two stages: first create required rnodes, then flush, then
            # update their scores?
            session.flush()
        return rnode

    @property
    def parent(self):
        if self.qnode.parent is None:
            return None
        return ResponseNode.from_qnode(self.qnode.parent, self.submission)

    @property
    def children(self):
        for child_qnode in self.qnode.children:
            rnode = ResponseNode.from_qnode(child_qnode, self.submission)
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
            response = Response.from_measure(qnode_measure, self.submission)
            if response is not None:
                yield response

    def lineage(self):
        return [
            ResponseNode.from_qnode(q, self.submission_id)
            for q in self.qnode.lineage()]

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
        # Use qnodes instead of rnodes for lineage, because rnode.id is not
        # part of the API.
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
    response_parts = Column(JSON, default=list, nullable=False)
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
            [
                'program_id',
                'survey_id',
                'measure_id'],
            [
                'qnode_measure.program_id',
                'qnode_measure.survey_id',
                'qnode_measure.measure_id'],
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
    )

    user = relationship(AppUser)

    @classmethod
    def from_measure(cls, qnode_measure, submission):
        submission_id = to_id(submission)
        return (
            object_session(qnode_measure).query(cls)
            .get((submission_id, qnode_measure.measure_id)))

    @property
    def parent(self):
        return ResponseNode.from_qnode(
            self.qnode_measure.qnode, self.submission)

    @validates('response_parts')
    def validate_response_parts(self, k, s):
        return validate_with_humanized_errors(s, response_type.response_schema)

    def lineage(self):
        return ([
            ResponseNode.from_qnode(q, self.submission_id)
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
ResponseHistory.ob_type = property(lambda self: 'response')
# ResponseHistory.user = relationship(AppUser, passive_deletes=True)


class Attachment(Base):
    __tablename__ = 'attachment'
    id = Column(GUID, default=GUID.gen, primary_key=True)
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


Submission.survey = relationship(
    Survey,
    primaryjoin=(foreign(Submission.survey_id) == Survey.id) &
                (Submission.program_id == Survey.program_id))

Submission.responses = relationship(
    Response, backref='submission', passive_deletes=True)


ResponseNode.qnode = relationship(
    QuestionNode,
    primaryjoin=(
        (foreign(ResponseNode.qnode_id) == QuestionNode.id) &
        (ResponseNode.program_id == QuestionNode.program_id)))


Response.qnode_measure = relationship(QnodeMeasure)

Response.measure = association_proxy('qnode_measure', 'measure')
