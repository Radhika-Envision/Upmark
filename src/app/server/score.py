from response_type import ResponseError, ResponseType


INF = float('inf')


def is_cyclic(measure, path=None):
    '''@return True iff the measure has a cyclic dependency'''
    if path is None:
        path = []

    for var in measure.target_vars:
        if var.target_measure in path:
            return True
        if is_cyclic(var.target_measure, path + [var.target_measure], visited):
            return True
    return False


class GraphCalculator:
    '''
    Calculates submission scores.

    A survey is composed of two graphs:

     - The hierarchy, which starts with the survey, then various levels of
       rnodes, and has measures at the bottom. Everything in this graph is
       ultimately connected to the root (survey).

     - The dependency graph, which only contains measures. Measures can
       depend on other measures, or they may stand alone.

    Together these form a single graph. This calculator solves the graph. To
    use it:

     1. Make changes to some rnodes and responses.
     2. Mark them as dirty in the calculator using the `mark_dirty` method.
     3. Call `execute`.

    This class is safe to use with graphs with cycles in them - but the
    results will be non-deterministic.
    '''

    def __init__(self):
        self.rts = {}
        self.node_parents = {}
        self.dirty_set = set()
        self.graph_depths = {}
        self.graph = []

    def execute(self):
        '''
        Recalculate all dirty nodes. This is done in dependency order.
        '''
        self.graph.sort(key=lambda entry: entry[0:2])
        for _, node in self.graph:
            if self.node_type(node) == 'submission':
                self.calc_submission(node)
            elif self.node_type(node) == 'rnode':
                self.calc_response(node)
            else:
                self.calc_rnode(node)

    def mark_dirty(self, node, include_dependencies=False):
        '''
        Add a node to the graph for recalculation.
        @param include_dependencies recalculate the dependencies too.
        '''
        if node in dirty_set:
            return

        # Just add it to the graph; it will be sorted later by depth.
        self.graph.append((self.graph_depth(node), node))
        self.dirty_set.add(node)

        if include_dependencies:
            for dependency in self.dependencies(node):
                self.mark_dirty(dependency, True)

        for dependant in self.dependants(node):
            self.mark_dirty(dependant)

    def dependencies(self, node):
        '''
        @return an iterator over the direct dependencies of a node.
        '''
        if self.node_type(node) == 'submission':
            yield from node.responses
        elif self.node_type(node) == 'rnode':
            yield from node.children
            yield from node.responses

    def dependants(self, node):
        '''
        @return an iterator over the direct dependants of a node.
        '''
        if self.node_type(node) == 'submission':
            pass
        elif self.node_type(node) == 'rnode':
            parent = self.get_parent(node)
            if node.parent is not None:
                yield node.parent
            else:
                yield node.submission
        else:
            yield node.parent
            yield from (var.target_measure for var in node.target_vars)

    def graph_depth(self, node):
        '''
        @return the depth of a node in the dependency graph. Leaf nodes
        have a depth of -1; the next level is -2, then -3 and so on.
        '''
        depth = self.graph_depths.get(node)
        if depth is not None:
            return depth

        if self.node_type(node) == 'submission':
            depth = (INF, 0)
        elif self.node_type(node) == 'rnode':
            depth = (INF, self.graph_depth(parent) - 1)
        else:
            depth = (min((self.graph_depth(var.target_measure)
                          for var in node.target_vars), default=0) - 1,
                     -INF)

        self.graph_depths[node] = depth
        return depth

    def get_parent(self, node):
        '''
        Get the parent of a node.
        '''
        parent = self.node_parents.get(node)
        if parent is not None:
            return parent

        if self.node_type(node) == 'submission':
            parent = None
        elif self.node_type(node) == 'rnode':
            parent = node.parent
            if parent is None:
                parent = node.submission
        else:
            parent = node.parent

        self.node_parents[node] = parent
        return parent

    def get_rt(self, response_type):
        '''
        Convert a response type definition to a materialised response type.
        '''
        rt = self.rts.get(response_type)
        if rt is not None:
            return rt
        rt = ResponseType(
            response_type.name, response_type.parts, response_type.formula)
        self.rts[response_type] = rt
        return rt

    def calc_submission(self, submission):
        '''
        Calculate the score and metadata of a submission, and write them back
        to the submission object.
        '''
        stats = ResponseNodeStats()
        for c in submission.rnodes:
            stats.add_rnode(c)
        stats.to_submission(submission)

    def calc_rnode(self, rnode):
        '''
        Calculate the score and metadata of an rnode, and write them back
        to the rnode object.
        '''
        stats = ResponseNodeStats()
        for c in rnode.children:
            stats.add_rnode(c)
        for r in rnode.responses:
            stats.add_response(r)
        stats.to_rnode(rnode)

    def calc_response(self, response):
        '''
        Calculate the score and variables of a response, and write them back
        to the response object.
        '''
        rt = self.get_rt(response.measure.response_type)
        stats = ResponseStats(rt)
        stats.update(response)
        stats.to_response(response)

    def node_type(self, node):
        if hasattr(node, 'response_parts'):
            return 'response'
        if hasattr(node, 'submission_id'):
            return 'submission'
        return 'rnode'


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

    def update(self, response):
        if response.not_relevant:
            self.score = 0.0
            self.variables = {}
            return

        try:
            self.variables = self.response_type.variables(
                response.response_parts)
            self.response_type.validate(response_parts, scope)
            self.score = self.response_type.score(
                response.response_parts, self.variables)
        except ResponseTypeError as e:
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
