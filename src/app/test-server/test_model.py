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
                    check_qnodes(h1['id'], True)

            def check_qnodes(parent_id, parent_is_hierarchy):
                # Check duplicated qnodes
                if parent_is_hierarchy:
                    url = "/qnode.json?surveyId=%s&hierarchyId=%s"
                else:
                    url = "/qnode.json?surveyId=%s&parentId=%s"
                original_qnode_sons = self.fetch(
                    url % (original_survey_id, parent_id), method='GET',
                    expected=200, decode=True)
                new_qnode_sons = self.fetch(
                    url % (new_survey_id, parent_id), method='GET',
                    expected=200, decode=True)

                for q1, q2 in zip(original_qnode_sons, new_qnode_sons):
                    self.assertEqual(q1['id'], q2['id'])
                    self.assertEqual(q1['title'], q2['title'])
                    check_qnodes(q1['id'], False)
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
