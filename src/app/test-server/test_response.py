import json
import logging
import os
import pprint
import unittest
from unittest import mock
import urllib

from sqlalchemy.sql import func
from sqlalchemy.orm.session import make_transient
from tornado.escape import json_encode
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

import app
import base
import model
from response_type import ExpressionError, ResponseTypeCache, ResponseError
from utils import ToSon


log = logging.getLogger('app.test_response')


class ResponseTypeTest(unittest.TestCase):
    def setUp(self):
        proj_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

        with open(os.path.join(
                proj_dir, 'server', 'aquamark_response_types.json')) as file:
            self.aq_rts = ResponseTypeCache(json.load(file))

        with open(os.path.join(
                proj_dir, 'client', 'default_response_types.json')) as file:
            self.simple_rts = ResponseTypeCache(json.load(file))

    def test_comment_only(self):
        rt = self.simple_rts['comment']
        self.assertEqual(rt.calculate_score([]), 0.0)

    def test_yesno(self):
        rt = self.simple_rts['yes-no']
        self.assertEqual(rt.calculate_score([
            {'index': 0}
        ]), 0.0)

        self.assertEqual(rt.calculate_score([
            {'index': 1}
        ]), 1.0)

    def test_four_option(self):
        rt = self.aq_rts['business-support-1']
        self.assertEqual(rt.calculate_score([
            {'index': 0}
        ]), 0.2)

        self.assertEqual(rt.calculate_score([
            {'index': 1}
        ]), 0.4)

        self.assertEqual(rt.calculate_score([
            {'index': 2}
        ]), 0.6)

        self.assertEqual(rt.calculate_score([
            {'index': 3}
        ]), 0.8)

        self.assertEqual(rt.calculate_score([
            {'index': 4}
        ]), 1.0)

    def test_multipart(self):
        rt = self.aq_rts['standard']
        self.assertAlmostEqual(rt.calculate_score([
            {'index': 0},
            {'index': 0},
            {'index': 0},
            {'index': 0},
        ]), (0.48 + 0.12) * (0.12 + 0.08))

        self.assertAlmostEqual(rt.calculate_score([
            {'index': 4},
            {'index': 3},
            {'index': 2},
            {'index': 1},
        ]), (0.80 + 0.18) * (0.36 + 0.16))

    def test_missing_part(self):
        with self.assertRaises(ResponseError):
            self.simple_rts['yes-no'].calculate_score([])

        with self.assertRaises(ResponseError):
            self.aq_rts['standard'].calculate_score([
                {'index': 4},
                {'index': 3},
                {'index': 2},
            ])

    def test_missing_option(self):
        with self.assertRaises(ResponseError):
            self.simple_rts['yes-no'].calculate_score([
                {'index': 2},
            ])
        with self.assertRaises(ResponseError):
            self.simple_rts['yes-no'].calculate_score([
                {'index': -1},
            ])

    def test_predicate_violation(self):
        with self.assertRaises(ResponseError):
            self.aq_rts['standard'].calculate_score([
                {'index': 2},
                {'index': 4},
                {'index': 4},
                {'index': 4},
            ])


class AssessmentModelTest(base.AqModelTestBase):

    def test_response(self):
        with model.session_scope() as session:
            survey = session.query(model.Survey).first()
            self.assertEqual(len(survey.hierarchies), 2)
            h = survey.hierarchies[0]
            self.assertEqual(h.title, "Hierarchy 1")
            self.assertEqual(len(h.qnodes), 2)

            self.assertEqual(h.qnodes[1].seq, 1)
            q = h.qnodes[0]
            self.assertEqual(q.title, "Function 1")
            self.assertEqual(q.seq, 0)
            self.assertEqual(len(q.children), 1)
            self.assertEqual(len(q.measures), 0)

            q = q.children[0]
            self.assertEqual(q.title, "Process 1")
            self.assertEqual(q.seq, 0)
            self.assertEqual(len(q.children), 0)
            self.assertEqual(len(q.measures), 2)

            # Test association proxy from measure to qnode (via qnode_measure)
            self.assertEqual(q.qnode_measures[0].seq, 0)
            self.assertEqual(q.qnode_measures[1].seq, 1)
            m = q.measures[0]
            self.assertEqual(m.title, "Foo Measure")
            self.assertIn(q, m.parents)

            # Test association proxy from qnode to measure (via qnode_measure)
            self.assertEqual(m.parents[0], q)


class AssessmentTest(base.AqHttpTestBase):
    pass
