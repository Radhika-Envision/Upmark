class DagError(Exception):
    def __init__(self, *args, ops=None, node=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.ops = ops
        self.node = node


INFINITY = float('Inf')


class Graph:
    def __init__(self, graph):
        self.graph = graph

    def evaluate(self):
        for meta in self.graph:
            if meta.depth == INFINITY:
                meta.ops.cyclic(meta.node, meta.dependencies, meta.dependants)
            else:
                meta.ops.evaluate(meta.node, meta.dependencies, meta.dependants)


class GraphBuilder:
    '''
    Organises nodes into a graph for evaluation in topological (dependency)
    order.

    1. Add nodes using the add method, then add some graph edges to the
       object that is returned.
    2. Call `build` to get a compiled and sorted graph object.

    This class is safe to use with graphs with cycles in them - but the
    results will be non-deterministic.
    '''

    def __init__(self):
        self.nodes = {}

    def build(self):
        nodes_b = {}
        def get_depth(meta):
            if meta.depth is not None:
                return meta.depth
            meta.depth = INFINITY
            deps = meta.dependencies
            meta.depth = max((get_depth(nodes_b[b]) + 1 for b in deps), default=0)
            return meta.depth

        for node, meta in self.nodes.items():
            nodes_b[node] = NodeMeta(node, meta.dependants.copy(), meta.ops)

        for meta_b in nodes_b.values():
            for dependant in meta_b.dependants:
                nodes_b[dependant].dependencies.add(meta_b.node)

        for meta_b in nodes_b.values():
            get_depth(meta_b)

        graph = sorted(nodes_b.values(), key=lambda meta: meta.depth)

        return Graph(graph)

    def add_recursive(self, node, node_builder):
        if node in self.nodes:
            return
        meta = self.add(node).with_ops(node_builder.ops(node))
        for dependant, builder in node_builder.dependants(node):
            meta.with_dependant(dependant)
            self.add_recursive(dependant, builder)

    def add(self, node):
        meta = self.nodes.get(node)
        if meta is not None:
            return meta
        meta = ProtoNodeMeta()
        self.nodes[node] = meta
        return meta


class ProtoNodeMeta:
    __slots__ = ('dependants', 'ops')
    def __init__(self,):
        self.dependants = set()
        self.ops = NOOP

    def with_dependant(self, node):
        self.dependants.add(node)
        return self

    def with_ops(self, ops):
        self.ops = ops
        return self


class NodeMeta:
    __slots__ = ('dependants', 'dependencies', 'depth', 'node', 'ops')
    def __init__(self, node, dependants, ops):
        self.node = node
        self.dependants = dependants
        self.dependencies = set()
        self.ops = ops
        self.depth = None

    def __repr__(self):
        return "NodeMeta(%s: %s)" % (self.depth, self.node)


class NodeBuilder:
    def dependants(self, node):
        '''
        Returns:
            An iterator over the direct dependants of a node (towards the
            sinks / results). Any given dependant may appear in the sequence
            more than once.
        '''
        yield from ()

    def ops(self, node):
        return NOOP


class Ops:
    '''
    Performs typed operations on a node in the graph.
    '''

    def evaluate(self, node, dependencies, dependants):
        '''
        Process a node. All of the node's dependencies will have been
        evaluated before this is called.
        '''
        pass

    def cyclic(self, node, dependencies, dependants):
        '''
        Called instead of evaluate when a node is part of (or is downstream
        from) a cyclic dependency.
        '''
        raise DagError("Cyclic dependency", ops=self, node=node)

    def __repr__(self):
        return "Ops"


class OpsProxy:
    '''
    An ops object that can be bound to a node in the tree, but whose operation
    can be replaced later.
    '''

    def __init__(self, ops=None):
        self.ops = ops or NOOP

    def evaluate(self, node, dependencies, dependants):
        self.ops.evaluate(node, dependencies, dependants)

    def cyclic(self, node, dependencies, dependants):
        self.ops.evaluate(node, dependencies, dependants)

    def __repr__(self):
        return repr(self.ops)


NOOP = Ops()
