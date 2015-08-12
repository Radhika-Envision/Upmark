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
from utils import ToSon


log = logging.getLogger('app.test_model')


class SurveyStructureTest(base.AqModelTestBase):

    def test_traverse_structure(self):
        # Read from database
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

#            to_son = ToSon(include=[
#                r'/title$',
#                r'/description$',
#                r'/seq$',
#                r'/intent$',
#                r'/weight$',
#                r'/response_type$',
#                # Descend
#                r'/hierarchies$',
#                r'/qnodes$',
#                r'/children$',
#                r'/measures$',
#                r'/measure_seq$',
#                r'/[0-9]+$',
#            ])
#            pprint.pprint(to_son(survey), width=120)

    def test_list_measures(self):
        with model.session_scope() as session:
            survey = session.query(model.Survey).first()
            measures = session.query(model.Measure)\
                .filter(model.Measure.survey_id == survey.id)\
                .all()
            self.assertEqual(len(measures), 3)

    def test_unlink_measure(self):
        with model.session_scope() as session:
            survey = session.query(model.Survey).first()
            q = survey.hierarchies[0].qnodes[0].children[0]
            self.assertEqual(len(q.measures), 2)
            self.assertEqual(q.measures[0].title, "Foo Measure")
            self.assertEqual(q.qnode_measures[0].seq, 0)
            self.assertEqual(q.measures[1].title, "Bar Measure")
            self.assertEqual(q.qnode_measures[1].seq, 1)
            q.measures.remove(q.measures[0])
            # Alter sequence: remove first element, and confirm that sequence
            # numbers update.
            session.flush()
            self.assertEqual(len(q.measures), 1)
            self.assertEqual(q.measures[0].title, "Bar Measure")
            self.assertEqual(q.qnode_measures[0].seq, 0)

    def test_orphan_measure(self):
        with model.session_scope() as session:
            survey = session.query(model.Survey).first()
            q = survey.hierarchies[0].qnodes[0].children[0]
            q.measures.remove(q.measures[0])

        # Find orphans using outer join
        with model.session_scope() as session:
            survey = session.query(model.Survey).first()
            measures = session.query(model.Measure)\
                .outerjoin(model.QnodeMeasure)\
                .filter(model.Measure.survey_id == survey.id)\
                .filter(model.QnodeMeasure.qnode_id == None)\
                .all()
            self.assertEqual(len(measures), 1)
            m = measures[0]
            self.assertEqual(m.title, "Foo Measure")

        # Find non-orphans using inner join
        with model.session_scope() as session:
            survey = session.query(model.Survey).first()
            measures = session.query(model.Measure)\
                .join(model.QnodeMeasure)\
                .filter(model.Measure.survey_id == survey.id)\
                .order_by(model.Measure.title)\
                .all()
            self.assertEqual(len(measures), 2)
            m = measures[0]
            self.assertEqual(m.title, "Bar Measure")
            m = measures[1]
            self.assertEqual(m.title, "Baz Measure")

    def test_history(self):
        # Duplicate a couple of objects
        with model.session_scope() as session:
            survey = session.query(model.Survey).first()
            hierarchy = survey.hierarchies[0]
            session.expunge(survey)
            make_transient(survey)
            session.expunge(hierarchy)
            make_transient(hierarchy)

            survey.id = None
            survey.created = None
            survey.title = 'Duplicate survey'
            session.add(survey)
            session.flush()

            hierarchy.title = 'Duplicate hierarchy'
            hierarchy.survey = survey

        # Make sure hierarchy ID is still the same
        with model.session_scope() as session:
            surveys = session.query(model.Survey).all()
            self.assertNotEqual(surveys[0].id, surveys[1].id)
            self.assertNotEqual(
                surveys[0].hierarchies[0].survey_id,
                surveys[1].hierarchies[0].survey_id)
            self.assertEqual(
                surveys[0].hierarchies[0].id,
                surveys[1].hierarchies[0].id)

        # Get all surveys for some hierarchy ID
        with model.session_scope() as session:
            # This hierarchy was duplicated, and should be in two surveys.
            hierarchy = (session.query(model.Hierarchy)
                .filter_by(title="Hierarchy 1")
                .one())
            surveys = (session.query(model.Survey)
                .join(model.Hierarchy)
                .filter(model.Hierarchy.id==hierarchy.id)
                .all())
            titles = {s.title for s in surveys}
            self.assertEqual(titles, {"Duplicate survey", "Test Survey 1"})

            # This one was not, so it should only be in the first.
            hierarchy = (session.query(model.Hierarchy)
                .filter_by(title="Hierarchy 2")
                .one())
            surveys = (session.query(model.Survey)
                .join(model.Hierarchy)
                .filter(model.Hierarchy.id==hierarchy.id)
                .all())
            titles = {s.title for s in surveys}
            self.assertEqual(titles, {"Test Survey 1"})


class SurveyTest(base.AqHttpTestBase):

    def test_list_surveys(self):
        with base.mock_user('clerk'):
            survey_sons = self.fetch(
                "/survey.json", method='GET',
                expected=200, decode=True)
            self.assertEqual(len(survey_sons), 1)

            survey_sons = self.fetch(
                "/survey.json?open=true", method='GET',
                expected=200, decode=True)
            self.assertEqual(len(survey_sons), 0)

            survey_sons = self.fetch(
                "/survey.json?editable=true", method='GET',
                expected=200, decode=True)
            self.assertEqual(len(survey_sons), 1)

    def test_duplicate_survey(self):
        with base.mock_user('author'):
            survey_sons = self.fetch(
                "/survey.json", method='GET',
                expected=200, decode=True)
            self.assertEqual(len(survey_sons), 1)
            original_survey_id = survey_sons[0]['id']

            survey_son = self.fetch(
                "/survey/%s.json" % original_survey_id, method='GET',
                expected=200, decode=True)

            survey_son['title'] = "Duplicate survey"

            survey_son = self.fetch(
                "/survey.json?duplicateId=%s" % original_survey_id,
                method='POST', body=json_encode(survey_son),
                expected=200, decode=True)
            new_survey_id = survey_son['id']
            self.assertNotEqual(original_survey_id, new_survey_id)

            def check_hierarchies():
                # Check duplicated hierarchies
                original_hierarchy_sons = self.fetch(
                    "/hierarchy.json?surveyId=%s" % original_survey_id,
                    method='GET',
                    expected=200, decode=True)
                new_hierarchy_sons = self.fetch(
                    "/hierarchy.json?surveyId=%s" % new_survey_id, method='GET',
                    expected=200, decode=True)

                for h1, h2 in zip(original_hierarchy_sons, new_hierarchy_sons):
                    self.assertEqual(h1['id'], h2['id'])
                    self.assertEqual(h1['title'], h2['title'])
                    check_qnodes(h1['id'], '')

            def check_qnodes(hierarchy_id, parent_id):
                # Check duplicated qnodes
                url = "/qnode.json?surveyId=%s&hierarchyId=%s&parentId=%s"
                original_qnode_sons = self.fetch(
                    url % (original_survey_id, hierarchy_id, parent_id),
                    method='GET', expected=200, decode=True)
                new_qnode_sons = self.fetch(
                    url % (new_survey_id, hierarchy_id, parent_id),
                    method='GET', expected=200, decode=True)

                for q1, q2 in zip(original_qnode_sons, new_qnode_sons):
                    self.assertEqual(q1['id'], q2['id'])
                    self.assertEqual(q1['title'], q2['title'])
                    check_qnodes(hierarchy_id, q1['id'])
                    check_measures(q1['id'])

            def check_measures(parent_id):
                # Check duplicated measures
                url = "/measure.json?surveyId=%s&parentId=%s"
                original_measure_sons = self.fetch(
                    url % (original_survey_id, parent_id), method='GET',
                    expected=200, decode=True)
                new_measure_sons = self.fetch(
                    url % (new_survey_id, parent_id), method='GET',
                    expected=200, decode=True)

                for m1, m2 in zip(original_measure_sons, new_measure_sons):
                    self.assertEqual(m1['id'], m2['id'])
                    self.assertEqual(m1['title'], m2['title'])

            check_measures('')
            check_hierarchies()

        # Thoroughly test new relationships: make sure there is no
        # cross-referencing between new and old survey.
        with model.session_scope() as session:
            sa = session.query(model.Survey).get(original_survey_id)
            sb = session.query(model.Survey).get(new_survey_id)
            self.assertNotEqual(sa.id, sb.id)
            self.assertEqual(sa.tracking_id, sb.tracking_id)
            self.assertNotEqual(sa, sb)
            log.info("Visiting survey pair %s and %s", sa, sb)

            def visit_hierarchy(a, b):
                log.info("Visiting hierarchy pair %s and %s", a, b)
                self.assertEqual(a.id, b.id)
                self.assertNotEqual(a, b)

                self.assertEqual(a.survey_id, sa.id)
                self.assertEqual(b.survey_id, sb.id)
                self.assertEqual(a.survey, sa)
                self.assertEqual(b.survey, sb)

                self.assertEqual(len(a.qnodes), len(b.qnodes))
                for qa, qb in zip(a.qnodes, b.qnodes):
                    visit_qnode(qa, qb, a, b, None, None)

            def visit_qnode(a, b, ha, hb, pa, pb):
                log.info("Visiting qnode pair %s and %s", a, b)
                self.assertEqual(a.id, b.id)
                self.assertNotEqual(a, b)
                self.assertEqual(a.hierarchy_id, b.hierarchy_id)

                self.assertEqual(a.survey_id, sa.id)
                self.assertEqual(b.survey_id, sb.id)
                self.assertEqual(a.survey, sa)
                self.assertEqual(b.survey, sb)

                self.assertEqual(a.hierarchy_id, ha.id)
                self.assertEqual(b.hierarchy_id, hb.id)
                self.assertEqual(a.hierarchy, ha)
                self.assertEqual(b.hierarchy, hb)

                if pa is not None:
                    self.assertEqual(a.parent_id, pa.id)
                    self.assertEqual(b.parent_id, pb.id)
                self.assertEqual(a.parent, pa)
                self.assertEqual(b.parent, pb)

                self.assertEqual(len(a.children), len(b.children))
                for qa, qb in zip(a.children, b.children):
                    visit_qnode(qa, qb, ha, hb, a, b)

                self.assertEqual(len(a.qnode_measures), len(b.qnode_measures))
                for qma, qmb in zip(a.qnode_measures, b.qnode_measures):
                    visit_qnode_measure(qma, qmb, a, b)

                self.assertEqual(len(a.measures), len(b.measures))
                for ma, mb in zip(a.measures, b.measures):
                    visit_measure(ma, mb, None, None, a, b)

            def visit_qnode_measure(a, b, qa, qb):
                log.info("Visiting qnode_measure pair %s and %s", a, b)
                self.assertEqual(a.qnode_id, b.qnode_id)
                self.assertEqual(a.measure_id, b.measure_id)
                self.assertNotEqual(a.measure, b.measure)

                self.assertEqual(a.survey_id, sa.id)
                self.assertEqual(b.survey_id, sb.id)
                self.assertEqual(a.survey, sa)
                self.assertEqual(b.survey, sb)

                self.assertEqual(a.qnode_id, qa.id)
                self.assertEqual(b.qnode_id, qb.id)
                self.assertEqual(a.qnode, qa)
                self.assertEqual(b.qnode, qb)

                visit_measure(a.measure, b.measure, a, b, qa, qb)

            def visit_measure(a, b, qma, qmb, pa, pb):
                log.info("Visiting measure pair %s and %s", a, b)
                self.assertEqual(a.id, b.id)
                self.assertNotEqual(a, b)

                self.assertEqual(a.survey_id, sa.id)
                self.assertEqual(b.survey_id, sb.id)
                self.assertEqual(a.survey, sa)
                self.assertEqual(b.survey, sb)

                if qma is not None:
                    self.assertIn(qma, a.qnode_measures)
                    self.assertNotIn(qma, b.qnode_measures)
                    self.assertIn(qmb, b.qnode_measures)
                    self.assertNotIn(qmb, a.qnode_measures)

                if pa is not None:
                    self.assertIn(pa, a.parents)
                    self.assertNotIn(pa, b.parents)
                    self.assertIn(pb, b.parents)
                    self.assertNotIn(pb, a.parents)

            self.assertEqual(len(sa.measures), len(sb.measures))
            for a, b in zip(sa.measures, sb.measures):
                visit_measure(a, b, None, None, None, None)

            self.assertEqual(len(sa.hierarchies), len(sb.hierarchies))
            for a, b in zip(sa.hierarchies, sb.hierarchies):
                visit_hierarchy(a, b)
