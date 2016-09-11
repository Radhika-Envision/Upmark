'''
Calculates submission scores.

A survey is composed of two graphs:

- The hierarchy, which starts with the survey, then various levels of
rnodes, and has measures at the bottom. Everything in this graph is
ultimately connected to the root (survey).

- The dependency graph, which only contains measures. Measures can
depend on other measures, or they may stand alone.

Together these form a single graph. This module solves the graph.
'''

from datetime import datetime

from cache import instance_method_lru_cache
from response_type import ResponseError, ResponseType
from dag import Graph, GraphBuilder, NodeBuilder, Ops, OpsProxy


class ScoreError(Exception):
    pass


# Convenience classes


class Calculator:
    def __init__(self, config):
        self.config = config
        self.builder = GraphBuilder()

    @classmethod
    def structural(cls):
        config = GraphConfig()
        manifest = StructureManifest()
        config.with_manifest(manifest)
        return cls(config)

    @classmethod
    def scoring(cls, submission):
        config = GraphConfig()
        manifest = ScoreManifest(submission)
        config.with_manifest(manifest)
        return cls(config)

    def mark_program_dirty(self, program, force_dependants=False):
        self.builder.add_with_dependants(
            program, self.config.program_builder, force_dependants)

    def mark_survey_dirty(self, survey, force_dependants=False):
        self.builder.add_with_dependants(
            survey, self.config.survey_builder, force_dependants)

    def mark_entire_survey_dirty(self, survey):
        self.builder.add_with_dependencies(
            survey, self.config.survey_builder)

    def mark_qnode_dirty(self, qnode, force_dependants=False):
        self.builder.add_with_dependants(
            qnode, self.config.qnode_builder, force_dependants)

    def mark_measure_dirty(self, qnode_measure, force_dependants=False):
        self.builder.add_with_dependants(
            qnode_measure, self.config.measure_builder, force_dependants)

    def execute(self):
        graph = self.builder.build()
        graph.evaluate()


# Factories


class GraphConfig:
    def __init__(self):
        self.program_builder = ProgramBuilder(self)
        self.survey_builder = SurveyBuilder(self)
        self.qnode_builder = QnodeBuilder(self)
        self.measure_builder = MeasureBuilder(self)
        self.program_ops = OpsProxy()
        self.survey_ops = OpsProxy()
        self.qnode_ops = OpsProxy()
        self.measure_ops = OpsProxy()

    def with_manifest(self, manifest):
        self.program_ops.ops = manifest.program_ops
        self.survey_ops.ops = manifest.survey_ops
        self.qnode_ops.ops = manifest.qnode_ops
        self.measure_ops.ops = manifest.measure_ops
        return self


class StructureManifest:
    def __init__(self):
        self.program_ops = ProgramOps()
        self.survey_ops = SurveyOps()
        self.qnode_ops = QnodeOps()
        self.measure_ops = MeasureOps()


class ScoreManifest:
    def __init__(self, submission):
        self.program_ops = ProgramOps()
        self.survey_ops = SubmissionOps(submission)
        self.qnode_ops = RnodeOps(submission)
        self.measure_ops = ResponseOps(submission)


# Survey builders - these know how to recursively build a DAG from the survey
# structure.


class ProgramBuilder(NodeBuilder):
    def __init__(self, config):
        self.config = config

    def dependencies(self, program):
        yield from (
            (survey, self.config.survey_builder) for survey in program.surveys)

    def ops(self, survey):
        return self.config.program_ops


class SurveyBuilder(NodeBuilder):
    def __init__(self, config):
        self.config = config

    def dependants(self, survey):
        yield survey.program, self.config.program_builder

    def dependencies(self, survey):
        yield from (
            (qnode, self.config.qnode_builder) for qnode in survey.qnodes)

    def ops(self, survey):
        return self.config.survey_ops


class QnodeBuilder(NodeBuilder):
    def __init__(self, config):
        self.config = config

    def dependants(self, qnode):
        if qnode.parent is not None:
            yield qnode.parent, self
        else:
            yield qnode.survey, self.config.survey_builder

    def dependencies(self, qnode):
        yield from (
            (child, self) for child in qnode.children)
        yield from (
            (qnode_measure, self.config.measure_builder)
            for qnode_measure in qnode.qnode_measures)

    def ops(self, qnode):
        return self.config.qnode_ops


class MeasureBuilder(NodeBuilder):
    def __init__(self, config):
        self.config = config

    def dependants(self, qnode_measure):
        yield qnode_measure.qnode, self.config.qnode_builder
        yield from (
            (var.target_qnode_measure, self)
            for var in qnode_measure.target_vars)

    def dependencies(self, qnode_measure):
        yield from (
            (var.source_qnode_measure, self)
            for var in qnode_measure.source_vars)

    def ops(self, measure):
        return self.config.measure_ops


# Survey structure ops - these update survey structure metadata.


class ProgramOps(Ops):
    def evaluate(self, program, dependencies, dependants):
        pass


class SurveyOps(Ops):
    def evaluate(self, survey, dependencies, dependants):
        survey.n_measures = sum(qnode.n_measures for qnode in survey.qnodes)
        survey.modified = datetime.utcnow()


class QnodeOps(Ops):
    def evaluate(self, qnode, dependencies, dependants):
        total_weight = sum(qm.measure.weight for qm in qnode.qnode_measures)
        total_weight += sum(child.total_weight for child in qnode.children)
        n_measures = len(qnode.qnode_measures)
        n_measures += sum(child.n_measures for child in qnode.children)

        qnode.total_weight = total_weight
        qnode.n_measures = n_measures


class MeasureOps(Ops):
    def evaluate(self, qnode_measure, dependencies, dependants):
        pass


# Submission score ops - these update submission metadata (e.g. score).


class SubmissionOps(Ops):
    def __init__(self, submission):
        self.submission = submission

    def evaluate(self, survey, dependencies, dependants):
        assert(self.submission.survey == survey)
        stats = ResponseNodeStats()
        for c in self.submission.rnodes:
            stats.add_rnode(c)
        stats.to_submission(self.submission)


class RnodeOps(Ops):
    def __init__(self, submission):
        self.submission = submission

    def evaluate(self, qnode, dependencies, dependants):
        rnode = qnode.get_rnode(self.submission, create=True)
        stats = ResponseNodeStats()
        for child in rnode.children:
            stats.add_rnode(child)
        for response in rnode.responses:
            stats.add_response(response)
        stats.to_rnode(rnode)


class ResponseOps(Ops):
    def __init__(self, submission):
        self.submission = submission

    def evaluate(self, qnode_measure, dependencies, dependants):
        measure = qnode_measure.measure
        response = self.get_response(qnode_measure)
        response_type = self.get_response_type(measure.response_type)
        scope = self.external_variables(response, qnode_measure)
        stats = ResponseStats(response_type)
        stats.update(response, scope)
        stats.to_response(response)

    @instance_method_lru_cache()
    def get_response(self, qnode_measure):
        return qnode_measure.get_response(self.submission)

    @instance_method_lru_cache()
    def get_response_type(self, response_type):
        '''
        Convert a response type definition to a materialised response type.
        '''
        return ResponseType(
            response_type.name, response_type.parts, response_type.formula)

    def external_variables(self, response, qnode_measure):
        scope = {}
        for var in qnode_measure.source_vars:
            source_response = self.get_response(var.source_qnode_measure)
            if source_response is None:
                raise ResponseError(
                    "Response %s depends on %s but it has not been filled in yet" %
                    (response.qnode_measure.get_path(),
                     source_response.qnode_measure.get_path()))
            value = source_response.variables.get(var.source_field)
            scope[var.target_field] = value
        return scope


class ResponseNodeStats:
    def __init__(self):
        self.score = 0.0
        self.n_approved = 0
        self.n_reviewed = 0
        self.n_final = 0
        self.n_draft = 0
        self.n_not_relevant = 0
        self.max_importance = 0.0
        self.max_urgency = 0.0

    def add_rnode(self, rnode):
        self.score += rnode.score
        self.n_approved += rnode.n_approved
        self.n_reviewed += rnode.n_reviewed
        self.n_final += rnode.n_final
        self.n_draft += rnode.n_draft
        self.n_not_relevant += rnode.n_not_relevant
        self.max_importance = max(self.max_importance, rnode.max_importance or 0.0)
        self.max_urgency = max(self.max_importance, rnode.max_importance or 0.0)

    def add_response(self, response):
        self.score += response.score
        if response.approval in {'draft', 'final', 'reviewed', 'approved'}:
            self.n_draft += 1
        if response.approval in {'final', 'reviewed', 'approved'}:
            self.n_final += 1
        if response.approval in {'reviewed', 'approved'}:
            self.n_reviewed += 1
        if response.approval in {'approved'}:
            self.n_approved += 1
        if response.not_relevant:
            self.n_not_relevant += 1

    def to_rnode(self, rnode):
        rnode.score = self.score
        rnode.n_approved = self.n_approved
        rnode.n_reviewed = self.n_reviewed
        rnode.n_final = self.n_final
        rnode.n_draft = self.n_draft
        rnode.n_not_relevant = self.n_not_relevant
        rnode.max_importance = rnode.importance or self.max_importance
        rnode.max_urgency = rnode.urgency or self.max_urgency

    def to_submission(self, submission):
        pass


class ResponseStats:
    def __init__(self, response_type):
        self.score = 0.0
        self.variables = {}
        self.response_type = response_type

    def update(self, response, scope):
        if response.not_relevant:
            self.score = 0.0
            self.variables = {}
            return

        try:
            self.variables = self.response_type.variables(
                response.response_parts)
            scope = scope.copy()
            scope.update(self.variables)
            self.response_type.validate(response.response_parts, scope)
            self.score = self.response_type.score(
                response.response_parts, self.variables)
        except Exception as e:
            raise ResponseError(
                "Could not calculate score for response %s %s: %s" %
                (response.qnode_measure.get_path(),
                 response.measure.title, str(e)))

    def to_response(self, response):
        response.score = self.score * response.measure.weight
        response.variables = self.variables
        response.variables['_raw'] = self.score
        response.variables['_score'] = self.score * response.measure.weight
        response.variables['_weight'] = response.measure.weight
