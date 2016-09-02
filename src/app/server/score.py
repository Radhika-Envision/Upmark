from response_type import ResponseError, ResponseType


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


# def deep_targets(measure):
#     '''@returns an iterator over target (dependency) measures (depth first)'''
#     q = [var.target for var in measure.target_vars]
#     while len(q):
#         measure = q.pop()
#         yield measure
#         q.extend((var.target for var in measure.target_vars))


class Calculator:
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

     1. Make changes to some rnodes and respones.
     2. Mark them as dirty in the calculator using the `mark_rnode_dirty` and
        `mark_response_dirty` methods.
     3. Call `execute`.

    If the entire submission needs to be recalculated, e.g. if the survey itself
    has changed, call `mark_submission_dirty` instead.
    '''

    def __init__(self):
        self.rts = {}

        self.dirty_rnode_levels = []
        self.dirty_rnode_set = set()
        self.rnode_depths = {}
        self.rnode_parents = {}

        self.dirty_response_set = set()
        self.inverse_graph_depths = {}
        self.graph = []

    def execute(self):
        '''
        Recalculate all dirty nodes. This is done in dependency order.
        '''
        # First calculate response scores and variables.
        # Sort reponses by the depth of their dependants, such that the deepest
        # items get evaluated first. The more negative items are deeper.
        self.graph.sort(key=lambda entry: entry[0])
        for _, response in self.graph:
            self.calc_response(response)

        # Now propagate scores up the tree.
        for rnode in itertools.chain(reversed(self.dirty_rnode_levels)):
            self.calc_rnode(rnode)

    def mark_submission_dirty(self, submission):
        '''
        Mark all responses in the submission as dirty. This will result in a
        full recalculation.
        '''
        for response in submission.responses:
            self.mark_response_dirty(response)

    def mark_response_dirty(self, response):
        '''
        Mark a response as dirty. All dependant responses and ancestor rnodes
        will also be marked as dirty.
        '''
        if response in self.dirty_response_set:
            return

        for target in response.measure.target_vars:
            target_response = target.target_measure.get_response(response.submission)
            if target_response is not None:
                self.mark_response_dirty(target_response)
        self.mark_rnode_dirty(response.parent)
        self.graph.append((self.inverse_graph_depth(response.measure), response)
        self.dirty_response_set.add(response)

    def mark_rnode_dirty(self, rnode):
        '''
        Mark an rnode (category response) as dirty. All ancestor rnodes will
        also be marked as dirty.
        '''
        if rnode in self.dirty_rnode_set:
            return

        depth = self.hierarchy_depth(rnode)
        while len(self.dirty_rnode_levels) <= depth:
            self.dirty_rnode_levels.append([])

        parent = self.get_parent(rnode)
        if parent:
            self.mark_rnode_dirty(parent)
        self.dirty_rnode_levels[depth].append(rnode)
        self.dirty_rnode_set.add(rnode)

    def inverse_graph_depth(self, measure):
        '''
        @return the depth of a measure in the dependency graph. Leaf measures
        have a depth of -1; the next level is -2, then -3 and so on.
        '''
        depth = self.inverse_graph_depths.get(measure)
        if depth is not None:
            return depth

        depth = max((self.inverse_graph_depths(var.target_measure) for var in mesaure.target_vars), default=0)
        self.inverse_graph_depths[measure] = depth - 1
        return depth

    def hierarchy_depth(self, rnode):
        '''
        @return the depth of an rnode in the hierarchy.
        '''
        depth = self.rnode_depths.get(rnode)
        if depth is not None:
            return depth
        parent = self.get_parent(rnode)
        if parent is None:
            depth = 0
        else:
            depth = self.hierarchy_depth(parent)
        self.rnode_depths[rnode] = depth
        return depth

    def get_parent(self, rnode):
        '''
        Get the parent of an rnode.
        '''
        if rnode not in self.rnode_parents:
            self.rnode_parents[rnode] = rnode.parent
        return self.rnode_parents[rnode]

    def get_rt(self, response_type):
        '''
        Convert a response type definition to a materialised response type.
        '''
        if response_type not in self.rts:
            self.rts[response_type] = ResponseType(
                response_type.name, response_type.parts, response_type.formula)
        return self.rts[response_type]

    def calc_response(self, response):
        '''
        Calculate the score and variables of a response, and write them back
        to the response object.
        '''
        rt = self.get_rt(response.measure.response_type)
        stats = ResponseStats(rt)
        stats.update(response)
        stats.to_response(response)

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
