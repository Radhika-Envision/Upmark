__all__ = [
    'Measure',
    'MeasureVariable',
    'Program',
    'program_surveygroup',
    'PurchasedSurvey',
    'ResponseType',
    'Survey',
    'QnodeMeasure',
    'QuestionNode',
]

from datetime import datetime
from itertools import chain, zip_longest

from sqlalchemy import Boolean, Column, DateTime, Float, \
    ForeignKey, Index, Integer, JSON, Table, Text
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.orm import backref, foreign, relationship, remote, \
    validates
from sqlalchemy.orm.session import object_session
from sqlalchemy.schema import ForeignKeyConstraint, UniqueConstraint
from voluptuous import All, Length, Schema
from voluptuous.humanize import validate_with_humanized_errors

import response_type
from .observe import Observable
from .base import Base, to_id
from .guid import GUID
from .surveygroup import SurveyGroup
from .user import Organisation


class Program(Observable, Base):
    __tablename__ = 'program'
    id = Column(GUID, default=GUID.gen, primary_key=True)
    tracking_id = Column(GUID, default=GUID.gen, nullable=False)

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

    def closest_deleted_ancestor(self):
        if self.deleted:
            return self
        else:
            return None

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
            'purchased_surveys', passive_deletes=True,
            order_by=open_date.desc()))

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
    id = Column(GUID, default=GUID.gen, primary_key=True)
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
    def ordered_qnodes(self):
        '''Returns all categories in depth-first order'''
        for qnode in self.qnodes:
            yield from qnode.ordered_children
            yield qnode

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

    @property
    def surveygroups(self):
        return self.program.surveygroups

    def closest_deleted_ancestor(self):
        if self.deleted:
            return self
        else:
            return self.program.closest_deleted_ancestor()

    def __repr__(self):
        return "Survey(title={}, program={})".format(
            self.title, getattr(self.program, 'title', None))


Survey.organisations = association_proxy('purchased_surveys', 'organisation')
Organisation.surveys = association_proxy('purchased_surveys', 'survey')


class QuestionNode(Observable, Base):
    '''
    A program category; contains sub-categories and measures. Gives a program
    its structure. Both measures and sub-categories are ordered.
    '''
    __tablename__ = 'qnode'
    id = Column(GUID, default=GUID.gen, primary_key=True)
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

    def lineage(self):
        if self.parent_id:
            return self.parent.lineage() + [self]
        else:
            return [self]

    def get_path_tuple(self):
        return tuple(q.seq + 1 for q in self.lineage())

    def get_path(self):
        return " ".join("%d." % i for i in self.get_path_tuple())

    def closest_deleted_ancestor(self):
        if self.deleted:
            return self
        elif self.parent_id:
            return self.parent.closest_deleted_ancestor()
        else:
            return self.survey.closest_deleted_ancestor()

    @property
    def ordered_qnode_measures(self):
        '''Returns all qnode/measures in depth-first order'''
        for child in self.children:
            yield from child.ordered_qnode_measures
        yield from self.qnode_measures

    @property
    def ordered_children(self):
        '''Returns all categories in depth-first order'''
        for child in self.children:
            yield from child.ordered_children
            yield child

    @property
    def ob_type(self):
        return 'qnode'

    @property
    def ob_ids(self):
        return [self.id, self.program_id]

    @property
    def action_lineage(self):
        return [self.program, self.survey] + self.lineage()

    @property
    def surveygroups(self):
        return self.program.surveygroups

    def __repr__(self):
        return "QuestionNode(path={}, title={}, program={})".format(
            self.get_path(), self.title,
            getattr(self.program, 'title', None))


class Measure(Observable, Base):
    __tablename__ = 'measure'
    id = Column(GUID, default=GUID.gen, primary_key=True)
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
        return (
            object_session(self).query(QnodeMeasure)
            .get((self.program_id, sid, self.id)))

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

    @property
    def surveygroups(self):
        return self.program.surveygroups

    def __repr__(self):
        return "Measure(title={}, program={})".format(
            self.title, getattr(self.program, 'title', None))


class QnodeMeasure(Base):
    # This is an association object for qnodes <-> measures. Normally this
    # would be done with a raw table, but because we want access to the `seq`
    # column, it needs to be a mapped class.
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
        Index(
            'qnodemeasure_qnode_id_program_id_index',
            qnode_id, program_id),
        Index(
            'qnodemeasure_measure_id_program_id_index',
            measure_id, program_id),
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

    def get_path_tuple(self):
        return self.qnode.get_path_tuple() + (self.seq + 1,)

    def get_path(self):
        return " ".join("%d." % i for i in self.get_path_tuple())

    def closest_deleted_ancestor(self):
        return self.qnode.closest_deleted_ancestor()

    def __repr__(self):
        return (
            "QnodeMeasure(path={}, program={}, survey={}, measure={})"
            .format(
                self.get_path(),
                getattr(self.program, 'title', None),
                getattr(self.survey, 'title', None),
                getattr(self.measure, 'title', None)))


class ResponseType(Observable, Base):
    __tablename__ = 'response_type'
    id = Column(GUID, default=GUID.gen, primary_key=True)
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
    def validate_formula(self, k, formula):
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

    @property
    def surveygroups(self):
        return self.program.surveygroups

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


# Lists and Complex Relationships
#
# We need to give explicit join rules due to use of foreign key in composite
# primary keys. The foreign_keys argument is used to mark which columns are
# writable. For example, where a class has a program relationship that can
# write to the program_id column, the foreign_keys list for other relationships
# will not include the program_id column so that there is no ambiguity when
# both relationships are written to.
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


Survey.program = relationship(Program)

Program.surveys = relationship(
    Survey, back_populates='program', passive_deletes=True,
    order_by='Survey.title',
    primaryjoin=(
        (Program.id == Survey.program_id) &
        (Survey.deleted == False)))


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
    primaryjoin=(
        (foreign(QuestionNode.survey_id) == Survey.id) &
        (QuestionNode.program_id == Survey.program_id) &
        (QuestionNode.parent_id == None) &
        (QuestionNode.deleted == False)))


# The remote_side argument needs to be set on the many-to-one side, so it's
# easier to define this relationship from the perspective of the child, i.e.
# as QuestionNode.parent instead of QuestionNode.children. The backref still
# works. The collection arguments (passive_deletes, order_by, etc) need to be
# placed on the one-to-many side, so they are nested in the backref argument.
QuestionNode.parent = relationship(
    QuestionNode,
    primaryjoin=(
        (foreign(QuestionNode.parent_id) == remote(QuestionNode.id)) &
        (QuestionNode.program_id == remote(QuestionNode.program_id))))


QuestionNode.children = relationship(
    QuestionNode, back_populates='parent', passive_deletes=True,
    order_by=QuestionNode.seq, collection_class=ordering_list('seq'),
    primaryjoin=(
        (foreign(remote(QuestionNode.parent_id)) == QuestionNode.id) &
        (remote(QuestionNode.program_id) == QuestionNode.program_id) &
        (remote(QuestionNode.deleted) == False)))


QuestionNode.qnode_measures = relationship(
    QnodeMeasure, backref='qnode', cascade='all, delete-orphan',
    order_by=QnodeMeasure.seq, collection_class=ordering_list('seq'),
    primaryjoin=(
        (foreign(QnodeMeasure.qnode_id) == QuestionNode.id) &
        (QnodeMeasure.program_id == QuestionNode.program_id)))


Measure.qnode_measures = relationship(
    QnodeMeasure, backref='measure',
    primaryjoin=(
        (foreign(QnodeMeasure.measure_id) == Measure.id) &
        (QnodeMeasure.program_id == Measure.program_id)))


QnodeMeasure.survey = relationship(
    Survey,
    primaryjoin=(
        (foreign(QnodeMeasure.survey_id) == remote(Survey.id)) &
        (QnodeMeasure.program_id == remote(Survey.program_id))))


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
    cascade="all, delete-orphan",
    primaryjoin=(
        (foreign(MeasureVariable.source_measure_id) == QnodeMeasure.measure_id) &  # noqa: E501
        (MeasureVariable.survey_id == QnodeMeasure.survey_id) &
        (MeasureVariable.program_id == QnodeMeasure.program_id)))

# Dependants - yes, the target is the source. It's funny how that is.
QnodeMeasure.source_vars = relationship(
    MeasureVariable, backref='target_qnode_measure',
    cascade="all, delete-orphan",
    primaryjoin=(
        (foreign(MeasureVariable.target_measure_id) == QnodeMeasure.measure_id) &  # noqa: E501
        (MeasureVariable.survey_id == QnodeMeasure.survey_id) &
        (MeasureVariable.program_id == QnodeMeasure.program_id)))


MeasureVariable.survey = relationship(
    Survey,
    primaryjoin=(
        (foreign(MeasureVariable.survey_id) == Survey.id) &
        (MeasureVariable.program_id == Survey.program_id)))


Measure.response_type = relationship(
    ResponseType,
    primaryjoin=(
        (foreign(Measure.response_type_id) == ResponseType.id) &
        (ResponseType.program_id == Measure.program_id)))

ResponseType.measures = relationship(
    Measure, back_populates='response_type', passive_deletes=True,
    primaryjoin=(
        (foreign(Measure.response_type_id) == ResponseType.id) &
        (ResponseType.program_id == Measure.program_id)))


program_surveygroup = Table(
    'program_surveygroup', Base.metadata,
    Column('program_id', GUID, ForeignKey('program.id')),
    Column('surveygroup_id', GUID, ForeignKey('surveygroup.id')),
    Index('program_surveygroup_program_id_index', 'program_id'),
    Index('program_surveygroup_surveygroup_id_index', 'surveygroup_id'),
)


Program.surveygroups = relationship(
    SurveyGroup, backref='programs', secondary=program_surveygroup,
    collection_class=set,
    secondaryjoin=(
        (SurveyGroup.id == program_surveygroup.columns.surveygroup_id) &
        (SurveyGroup.deleted == False)))
