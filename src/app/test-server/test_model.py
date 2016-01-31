import logging
import os
import pprint
import unittest
from unittest import mock
import urllib

import sqlalchemy
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
            self.assertEqual(len(survey.measures), 5)
            h = survey.hierarchies[0]
            self.assertEqual(h.title, "Hierarchy 1")
            self.assertEqual(len(h.qnodes), 2)
            self.assertEqual(h.n_measures, 3)

            self.assertEqual(h.qnodes[1].seq, 1)
            q = h.qnodes[0]
            self.assertEqual(q.title, "Function 1")
            self.assertEqual(q.seq, 0)
            self.assertEqual(len(q.children), 2)
            self.assertEqual(len(q.measures), 0)
            self.assertEqual(q.n_measures, 3)

            q = q.children[0]
            self.assertEqual(q.title, "Process 1.1")
            self.assertEqual(q.seq, 0)
            self.assertEqual(len(q.children), 0)
            self.assertEqual(len(q.measures), 2)
            self.assertEqual(q.n_measures, 2)

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
            self.assertEqual(len(measures), 5)

    def test_unlink_measure(self):
        with model.session_scope() as session:
            survey = session.query(model.Survey).first()
            h = survey.hierarchies[0]
            q = h.qnodes[0].children[0]
            self.assertEqual(len(q.measures), 2)
            self.assertEqual(q.parent.n_measures, 3)
            self.assertEqual(q.measures[0].title, "Foo Measure")
            self.assertEqual(q.qnode_measures[0].seq, 0)
            self.assertEqual(q.measures[1].title, "Bar Measure")
            self.assertEqual(q.qnode_measures[1].seq, 1)
            q.measures.remove(q.measures[0])
            q.update_stats_ancestors()
            # Alter sequence: remove first element, and confirm that sequence
            # numbers update.
            session.flush()
            self.assertEqual(len(q.measures), 1)
            self.assertEqual(q.measures[0].title, "Bar Measure")
            self.assertEqual(q.qnode_measures[0].seq, 0)
            self.assertEqual(q.n_measures, 1)
            self.assertEqual(q.parent.n_measures, 2)
            self.assertEqual(h.n_measures, 2)

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
            measures = (session.query(model.Measure)
                .join(model.QnodeMeasure)
                .filter(model.Measure.survey_id == survey.id)
                .order_by(model.Measure.title)
                .all())
            self.assertEqual(len(measures), 4)
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
                "/survey.json?editable=true", method='GET',
                expected=200, decode=True)
            self.assertEqual(len(survey_sons), 1)

    def test_basic_query(self):
        with model.session_scope() as session:
            survey = session.query(model.Survey).first()
            h = survey.hierarchies[0]
            q = h.qnodes[0].children[0]
            q2 = h.qnodes[0].children[1]
            sid = str(survey.id)
            hid = str(h.id)
            qid = str(q.id)
            qid2 = str(q2.id)
            mid1 = str(q.measures[0].id)
            mid2 = str(q.measures[0].id)
            m3 = (session.query(model.Measure)
                .filter_by(title='Baz Measure')
                .one())
            mid3 = str(m3.id)
            user = (session.query(model.AppUser)
                    .filter_by(email='author')
                    .one())
            self.organisation_id = str(user.organisation.id)
            survey_id = survey.id
            hierarchy_id = h.id

        with base.mock_user('author'):
            # Query for qnodes based on deletion
            url = "/qnode.json?surveyId={}&hierarchyId={}".format(sid, hid)
            q_son = self.fetch(
                url,
                method='GET', expected=200, decode=True)
            self.assertEqual(len(q_son), 10)
            q_son = self.fetch(
                url + "&deleted=false",
                method='GET', expected=200, decode=True)
            self.assertEqual(len(q_son), 6)
            q_son = self.fetch(
                url + "&deleted=true",
                method='GET', expected=200, decode=True)
            self.assertEqual(len(q_son), 4)

            # Query for qnodes based on deletion again, this time taking parents
            # into account.
            url += "&level=1"
            q_son = self.fetch(
                url,
                method='GET', expected=200, decode=True)
            self.assertEqual(len(q_son), 6)
            q_son = self.fetch(
                url + "&deleted=false",
                method='GET', expected=200, decode=True)
            self.assertEqual(len(q_son), 2)
            q_son = self.fetch(
                url + "&deleted=true",
                method='GET', expected=200, decode=True)
            self.assertEqual(len(q_son), 4)


class ModifySurveyTest(base.AqHttpTestBase):

    def setUp(self):
        super().setUp()
        with model.session_scope() as session:
            survey = session.query(model.Survey).first()
            h = [h for h in survey.hierarchies if h.title == "Hierarchy 1"][0]
            qA, qB = h.qnodes
            qAA, qAB = qA.children
            self.sid = str(survey.id)
            self.hid = str(h.id)
            self.qidA, self.qidB, self.qidAA, self.qidAB = [
                str(q.id) for q in (qA, qB, qAA, qAB)]
            self.midAAA = str(qAA.measures[0].id)
            self.midAAB = str(qAA.measures[1].id)
            self.midABA = str(qAB.measures[0].id)
            user = (session.query(model.AppUser)
                    .filter_by(email='author')
                    .one())
            self.organisation_id = str(user.organisation.id)

        with base.mock_user('admin'):
            # need to purchase survey
            self.purchase_survey(self.hid, self.sid)

    def verify_stats(self):
        # Make sure stats match reality

        def qnodes(roots):
            # All qnodes in a tree (flattened list, depth-first)
            for root in roots:
                yield root
                for q in qnodes(root.children):
                    yield q

        def measures(roots):
            # All measures under a qnode
            for qn in qnodes(roots):
                for m in qn.measures:
                    yield m

        with model.session_scope() as session:
            for h in (session.query(model.Hierarchy)
                    .filter(model.Hierarchy.deleted == False)
                    .all()):
                for q in qnodes(h.qnodes):
                    n_measures = len(list(measures([q])))
                    weight = sum(m.weight for m in measures([q]))
                    log.debug(
                        "%s - N: actual: %d, cached: %d", q.title,
                        n_measures, q.n_measures)
                    log.debug(
                        "%s - W: actual: %d, cached: %d", q.title,
                        weight, q.total_weight)
                    self.assertEqual(n_measures, q.n_measures, q.title)
                    self.assertEqual(weight, q.total_weight, q.title)

    def test_unmodified_structure(self):
        self.verify_stats()
        with base.mock_user('author'):
            # Check current weights of qnode and measure
            q2_son = self.fetch(
                "/qnode/{}.json?surveyId={}".format(self.qidAB, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q2_son['total_weight'], 11)
            m_son = self.fetch(
                "/measure/{}.json?surveyId={}".format(self.midABA, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(m_son['weight'], 11)
            self.assertIn(self.qidAB, (p['id'] for p in m_son['parents']))
            self.assertNotIn(self.qidAA, (p['id'] for p in m_son['parents']))

    def test_modify_weight(self):
        with base.mock_user('author'):
            # Modify a measure's weight and check that the qnode weight is
            # updated
            m_son = self.fetch(
                "/measure/{}.json?surveyId={}".format(self.midAAA, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(m_son['weight'], 3)
            m_son['weight'] = 9
            m_son = self.fetch(
                "/measure/{}.json?surveyId={}".format(self.midAAA, self.sid),
                method='PUT', body=json_encode(m_son),
                expected=200, decode=True)
            self.assertAlmostEqual(m_son['weight'], 9)
            q_son = self.fetch(
                "/qnode/{}.json?surveyId={}".format(self.qidAA, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q_son['total_weight'], 15)
        self.verify_stats()

    def test_measure_move(self):
        with base.mock_user('author'):
            # Move measure to different parent and check that weights have moved
            m_son = self.fetch(
                "/measure/{}.json?surveyId={}&parentId={}".format(
                    self.midABA, self.sid, self.qidAA),
                method='PUT', body=json_encode({}),
                expected=200, decode=True)
            self.assertIn(self.qidAA, (p['id'] for p in m_son['parents']))
            self.assertNotIn(self.qidAB, (p['id'] for p in m_son['parents']))
            q_son = self.fetch(
                "/qnode/{}.json?surveyId={}".format(self.qidAA, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q_son['total_weight'], 20)
            q2_son = self.fetch(
                "/qnode/{}.json?surveyId={}".format(self.qidAB, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q2_son['total_weight'], 0)
        self.verify_stats()

    def test_delete_qnode(self):
        with base.mock_user('author'):
            # Delete a qnode and check that the parent weight is updated
            self.fetch(
                "/qnode/{}.json?surveyId={}".format(self.qidAA, self.sid),
                method='DELETE', expected=200)
            q_son = self.fetch(
                "/qnode/{}.json?surveyId={}".format(self.qidA, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q_son['total_weight'], 11)

            # Move a measure out of the deleted qnode...
            m_son = self.fetch(
                "/measure/{}.json?surveyId={}&parentId={}".format(
                    self.midAAA, self.sid, self.qidB),
                method='PUT', body=json_encode({}),
                expected=200, decode=True)
            q_son = self.fetch(
                "/qnode/{}.json?surveyId={}".format(self.qidA, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q_son['total_weight'], 11)
            q_son = self.fetch(
                "/qnode/{}.json?surveyId={}".format(self.qidB, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q_son['total_weight'], 3)

            self.verify_stats()

            # Undelete the qnode
            self.fetch(
                "/qnode/{}.json?surveyId={}".format(self.qidAA, self.sid),
                method='PUT', body=json_encode({}), expected=200)
            q_son = self.fetch(
                "/qnode/{}.json?surveyId={}".format(self.qidA, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q_son['total_weight'], 17)

            self.verify_stats()

    def test_delete_measure(self):
        with base.mock_user('author'):
            # Delete a measure and check that the qnode weight is updated
            self.fetch(
                "/measure/{}.json?surveyId={}&parentId={}".format(
                    self.midAAA, self.sid, self.qidAA),
                method='DELETE', expected=200)
            q_son = self.fetch(
                "/qnode/{}.json?surveyId={}".format(self.qidAA, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q_son['total_weight'], 6)

        self.verify_stats()

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
                with base.mock_user('admin'):
                    self.purchase_survey(hierarchy_id, original_survey_id)
                    self.purchase_survey(hierarchy_id, new_survey_id)

                with base.mock_user('author'):
                    # Check duplicated qnodes
                    url = ("/qnode.json?surveyId=%s&hierarchyId=%s&parentId=%s"
                           "&deleted=false")
                    if not parent_id:
                        url += '&root='
                    url1 = url % (original_survey_id, hierarchy_id, parent_id)
                    url2 = url % (new_survey_id, hierarchy_id, parent_id)
                    original_qnode_sons = self.fetch(
                        url1, method='GET', expected=200, decode=True)
                    new_qnode_sons = self.fetch(
                        url2, method='GET', expected=200, decode=True)

                    self.assertEqual(original_qnode_sons, new_qnode_sons,
                        "URL 1: %s\n" % url1
                        + "URL 2: %s" % url2)
                    for q1, q2 in zip(original_qnode_sons, new_qnode_sons):
                        log.info("q1: %s, q2: %s", q1, q2)
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

            # A has five measures, but two are only referenced by deleted nodes.
            self.assertEqual(len(sa.measures), 5)
            self.assertEqual(len(sb.measures), 3)
            measures_in_a = {m.id: m for m in sa.measures}
            for b in sb.measures:
                a = measures_in_a[b.id]
                visit_measure(a, b, None, None, None, None)

            # A has three hierarchies, but one is deleted.
            self.assertEqual(len(sa.hierarchies), 2)
            self.assertEqual(len(sb.hierarchies), 2)
            for a, b in zip(sa.hierarchies, sb.hierarchies):
                visit_hierarchy(a, b)
        self.verify_stats()

    def purchase_survey(self, hierarchy_id, survey_id):
        with model.session_scope() as session:
            user = (session.query(model.AppUser)
                .filter_by(email='admin')
                .one())
            organisation_id = str(user.organisation.id)

            self.fetch(
                "/organisation/%s/hierarchy/%s.json?surveyId=%s" %
                (organisation_id, hierarchy_id, survey_id),
                method='PUT', body='', expected=200)


class ReadonlySessionTest(base.AqModelTestBase):

    def test_readonly_session(self):
        with model.session_scope(readonly=True) as session:
            surveys = session.query(model.Survey).all()
            self.assertNotEqual(len(surveys), 0)

        with self.assertRaises(sqlalchemy.exc.ProgrammingError) as ecm, \
                model.session_scope(readonly=True) as session:
            session.query(model.SystemConfig).all()
        self.assertIn('permission denied', str(ecm.exception))

        with self.assertRaises(sqlalchemy.exc.ProgrammingError) as ecm, \
                model.session_scope(readonly=True) as session:
            session.execute("DELETE FROM measure")
        self.assertIn('permission denied', str(ecm.exception))

        with self.assertRaises(sqlalchemy.exc.ProgrammingError) as ecm, \
                model.session_scope(readonly=True) as session:
            session.execute("UPDATE measure SET title = 'foo'")
        self.assertIn('permission denied', str(ecm.exception))

        with self.assertRaises(sqlalchemy.exc.ProgrammingError) as ecm, \
                model.session_scope(readonly=True) as session:
            item = model.Measure(title='FOo')
            session.add(item)
        self.assertIn('permission denied', str(ecm.exception))
