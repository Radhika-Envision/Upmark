from itertools import repeat

import base
from dag import GraphBuilder, NodeBuilder, Ops, OpsProxy


class DagTest(base.LoggingTestCase):

    def test_simple(self):
        '''Test evaluation of a simple arithmetic tree'''
        builder = GraphBuilder()
        a = Value('a')
        b = Value('b')
        c = Value('c')
        ops = Sum()
        builder.add(c).with_ops(ops)
        builder.add(b).with_ops(ops).with_dependant(c)
        builder.add(a).with_ops(ops).with_dependant(c)
        builder.add(1).with_dependant(a)
        builder.add(2).with_dependant(a)
        builder.add(3).with_dependant(b)
        builder.add(4).with_dependant(b)
        graph = builder.build()
        graph.evaluate()
        self.assertEqual(a.value, 3)
        self.assertEqual(b.value, 7)
        self.assertEqual(c.value, 10)

    def test_disparate(self):
        '''Test evaluation of two disconnected graphs in a single object'''
        builder = GraphBuilder()
        a = Value('a')
        b = Value('b')
        ops = Sum()
        builder.add(b).with_ops(ops)
        builder.add(a).with_ops(ops)
        builder.add(1).with_dependant(a)
        builder.add(2).with_dependant(a)
        builder.add(3).with_dependant(b)
        builder.add(4).with_dependant(b)
        graph = builder.build()
        graph.evaluate()
        self.assertEqual(a.value, 3)
        self.assertEqual(b.value, 7)

    def test_proxy(self):
        '''Test replacement of operations after tree is built'''
        builder = GraphBuilder()
        a = Value('a')
        ops = OpsProxy()
        builder.add(a).with_ops(ops)
        builder.add(1).with_dependant(a)
        builder.add(2).with_dependant(a)
        graph = builder.build()
        graph.evaluate()
        self.assertEqual(a.value, 0)
        ops.ops = Sum()
        graph.evaluate()
        self.assertEqual(a.value, 3)

    def test_self_build(self):
        '''Build a tree from nodes that know how they are connected'''
        a = Value('a')
        b = Value('b')
        c = Value('c')
        one = Value('one', 1)
        two = Value('two', 2)
        three = Value('three', 3)
        four = Value('four', 4)

        a.dependants.append(c)
        b.dependants.append(c)
        one.dependants.append(a)
        two.dependants.append(a)
        three.dependants.append(b)
        four.dependants.append(b)

        builder = GraphBuilder()
        vbuilder = VBuilder()
        builder.add_with_dependants(one, vbuilder)
        builder.add_with_dependants(two, vbuilder)
        builder.add_with_dependants(three, vbuilder)
        builder.add_with_dependants(four, vbuilder)
        graph = builder.build()
        graph.evaluate()

        self.assertEqual(a.value, 3)
        self.assertEqual(b.value, 7)
        self.assertEqual(c.value, 10)

    def test_cyclic(self):
        '''Build a tree with cyclic nodes'''
        a = Value('a')
        b = Value('b')
        c = Value('c')
        one = Value('one', 1)
        two = Value('two', 2)
        three = Value('three', 3)
        four = Value('four', 4)

        a.dependants.append(c)
        a.dependants.append(one)
        b.dependants.append(c)
        one.dependants.append(a)
        two.dependants.append(a)
        three.dependants.append(b)
        four.dependants.append(b)

        builder = GraphBuilder()
        vbuilder = VBuilder()
        builder.add_with_dependants(one, vbuilder)
        builder.add_with_dependants(two, vbuilder)
        builder.add_with_dependants(three, vbuilder)
        builder.add_with_dependants(four, vbuilder)
        graph = builder.build()
        graph.evaluate()

        self.assertTrue(a.cyclic)
        self.assertTrue(c.cyclic)
        self.assertTrue(one.cyclic)

        self.assertFalse(b.cyclic)
        self.assertFalse(two.cyclic)
        self.assertFalse(three.cyclic)
        self.assertFalse(four.cyclic)


class Value:
    def __init__(self, name, value=0):
        self.name = name
        self.dependants = []
        self.cyclic = False
        self.value = value

    def __int__(self):
        return self.value

    def __repr__(self):
        if self.cyclic:
            return "Value(%s: C)" % self.name
        else:
            return "Value(%s: %s)" % (self.name, self.value)


class Sum(Ops):
    def evaluate(self, node, dependencies, _):
        if len(dependencies):
            node.value = sum((int(d) for d in dependencies))

    def __repr__(self):
        return "Sum"


class VBuilder(NodeBuilder):
    def __init__(self):
        self._ops = VSum()

    def dependants(self, node):
        yield from zip(node.dependants, repeat(self))

    def ops(self, node):
        return self._ops


class VSum(Ops):
    def evaluate(self, node, dependencies, dependants):
        if len(dependencies):
            node.value = sum((dep.value for dep in dependencies))
        node.cyclic = False

    def cyclic(self, node, dependencies, dependants):
        node.cyclic = True
