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
from dag import Graph, GraphBuilder, NodeBuilder, Ops


# Convenience classes


class SurveyUpdater:
    def __init__(self, survey):
        self.factory = SurveyGraphFactory(survey)
        self.builder = GraphBuilder()

    def mark_survey_dirty(self, survey):
        self.builder.add_recursive(survey, self.factory.survey_builder)

    def mark_qnode_dirty(self, qnode):
        self.builder.add_recursive(qnode, self.factory.qnode_builder)

    def mark_measure_dirty(self, measure):
        self.builder.add_recursive(measure, self.factory.measure_builder)

    def mark_all_measures_dirty(self, survey):
        for measure in survey.measures:
            self.builder.add_recursive(measure, self.factory.measure_builder)

    def execute(self):
        graph = self.builder.build()
        graph.evaluate()


class SubmissionUpdater(SurveyUpdater):
    def __init__(self, submission):
        self.factory = SubmissionGraphFactory(submission)
        self.builder = GraphBuilder()


# Factories


class SurveyGraphFactory:
    def __init__(self, survey):
        self.survey_builder = SurveyBuilder(self)
        self.qnode_builder = QnodeBuilder(self)
        self.measure_builder = MeasureBuilder(self, survey)
        self.survey_ops = SurveyOps(survey)
        self.qnode_ops = QnodeOps(survey)
        self.measure_ops = MeasureOps(survey)


class SubmissionGraphFactory(SurveyFactory):
    def __init__(self, submission):
        super().__init__(submission.survey)
        self.survey_ops = SubmissionOps(submission)
        self.qnode_ops = RnodeOps(submission)
        self.measure_ops = ResponseOps(submission)


# Structural stuff


class SurveyBuilder(NodeBuilder):
    def __init__(self, factory):
        self.factory = factory

    def ops(self, node):
        return self.factory.survey_ops


class QnodeBuilder(NodeBuilder):
    def __init__(self, factory):
        self.factory = factory

    def dependants(self, node):
        if node.parent is not None:
            yield node.parent, self
        else:
            yield node.survey, self.factory.qnode

    def ops(self, node):
        return self.factory.qnode_ops


class MeasureBuilder(NodeBuilder):
    def __init__(self, factory, survey):
        self.factory = factory
        self.survey = survey

    def dependants(self, node):
        yield node.get_parent(self.survey), self.factory.qnode
        yield from (var.target_measure, self for var in target_vars)

    def ops(self, node):
        return self.factory.measure_ops


# Survey structure ops


class SurveyOps(Ops):
    def __init__(self, survey):
        self.survey = survey

    def evaluate(self, node, _, _):
        node.n_measures = sum(qnode.n_measures for qnode in node.qnodes)
        node.modified = datetime.utcnow()


class QnodeOps(Ops):
    def __init__(self, survey):
        self.survey = survey

    def evaluate(self, node, _, _):
        total_weight = sum(measure.weight for measure in node.measures)
        total_weight += sum(child.total_weight for child in node.children)
        n_measures = len(node.measures)
        n_measures += sum(child.n_measures for child in node.children)

        node.total_weight = total_weight
        node.n_measures = n_measures


class MeasureOps(Ops):
    def __init__(self, survey):
        self.survey = survey

    def evaluate(self, node, _, _):
        pass


# Submission score ops


class SubmissionOps(Ops):
    def __init__(self, submission):
        self.submission = submission

    def evaluate(self, node, _, _):
        assert(self.submission.survey == node)
        stats = ResponseNodeStats()
        for c in self.submission.rnodes:
            stats.add_rnode(c)
        stats.to_submission(self.submission)


class RnodeOps(Ops):
    def __init__(self, submission):
        self.submission = submission

    def evaluate(self, node, _, _):
        rnode = node.get_rnode(self.submission)
        if rnode is None:
            rnode = ResponseNode(
                program=self.submission.program,
                submission=self.submission,
                qnode=qnode)
            object_session(self).add(rnode)
            object_session(self).flush()

        stats = ResponseNodeStats()
        for child in rnode.children:
            stats.add_rnode(child)
        for response in rnode.responses:
            stats.add_response(response)
        stats.to_rnode(rnode)


class ResponseOps(Ops):
    def __init__(self, submission):
        self.submission = submission

    def evaluate(self, node, _, _):
        response = self.get_response(node)
        response_type = self.get_response_type(node.response_type)
        scope = self.external_variables(response, node)
        stats = ResponseStats(response_type)
        stats.update(response, scope)
        stats.to_response(response)

    @instance_method_lru_cache()
    def get_response(self, measure):
        return measure.get_response(self.submission)

    def get_responses(self, measures):
        responses = (self.get_response(m) for m in measures)
        yield from (r for r in responses if r is not None)

    @instance_method_lru_cache()
    def get_response_type(self, response_type):
        '''
        Convert a response type definition to a materialised response type.
        '''
        return ResponseType(
            response_type.name, response_type.parts, response_type.formula)

    def external_variables(self, response, measure):
        scope = {}
        for var in measure.source_vars:
            source_response = self.get_response(var.source_measure)
            if source_response is None:
                raise ResponseError(
                    "Response %s depends on %s but it has not been filled in yet" %
                    (response.measure.get_path(response.submission.survey),
                     source_response.measure.get_path(response.submission.survey)))
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
            self.response_type.validate(response_parts, scope)
            self.score = self.response_type.score(
                response.response_parts, self.variables)
        except Exception as e:
            raise ResponseError(
                "Could not calculate score for response %s %s: %s" %
                (response.measure.get_path(response.submission.survey),
                 response.measure.title, str(e)))

     def to_response(self, response):
         response.score = self.score * response.measure.weight
         response.variables = self.variables
         response.variables['_raw'] = self.score
         response.variables['_score'] = self.score * response.measure.weight
         response.variables['_weight'] = response.measure.weight
