import os
import pprint
import unittest
from unittest import mock
import urllib

from sqlalchemy.sql import func

import model
from utils import ToSon


class SurveyStructureIntegrationTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        engine = model.connect_db(os.environ.get('DATABASE_URL'))
        engine.execute("DROP SCHEMA IF EXISTS public CASCADE")
        engine.execute("CREATE SCHEMA public")
        model.initialise_schema(engine)
        self.create_structure()

    def create_structure(self):
        # Create survey
        with model.session_scope() as session:
            survey = entity = model.Survey(
                title='Test Survey 1',
                description="This is a test survey")
            session.add(survey)
            session.flush()
            survey_id = survey.id

        # Create measures
        msons = [
            {
                'title': "Foo Measure",
                'intent': "Foo",
                'weight': 100,
                'response_type': 'A'
            },
            {
                'title': "Bar Measure",
                'intent': "Bar",
                'weight': 200,
                'response_type': 'A'
            },
            {
                'title': "Baz Measure",
                'intent': "Baz",
                'weight': 300,
                'response_type': 'A'
            },
        ]
        measure_ids = []
        with model.session_scope() as session:
            for mson in msons:
                measure = model.Measure(survey_id=survey_id, **mson)
                session.add(measure)
                session.flush()
                measure_ids.append(measure.id)

        # Create hierarchy, with qnodes and measures as descendants
        hsons = [
            {
                'title': "Hierarchy 1",
                'description': "Test",
                'qnodes': [
                    {
                        'title': "Function 1",
                        'description': "Test",
                        'children': [
                            {
                                'title': "Process 1",
                                'description': "Test",
                                'measures': [0, 1],
                            },
                        ],
                    },
                    {
                        'title': "Function 2",
                        'description': "Test",
                    },
                ],
            },
            {
                'title': "Hierarchy 2",
                'description': "Test",
                'qnodes': [
                    {
                        'title': "Section 1",
                        'description': "Test",
                        'children': [
                            {
                                'title': "SubSection 1",
                                'description': "Test",
                                'measures': [1, 2],
                            },
                        ],
                    },
                    {
                        'title': "Section 2",
                        'description': "Test",
                    },
                ],
            },
        ]

        def create_qnodes(qsons, session):
            qnodes = []
            for qson in qsons:
                qnode = model.QuestionNode(survey_id=survey_id)
                qnode.title = qson['title']
                qnode.description = qson['description']
                qnodes.append(qnode)
                session.add(qnode)
                session.flush()

                if 'children' in qson:
                    qnode.children = create_qnodes(qson['children'], session)
                    qnode.children.reorder()

                for i in qson.get('measures', []):
                    mi = measure_ids[i]
                    measure = session.query(model.Measure)\
                        .get((mi, survey_id))
                    qnode.measures.append(measure)
                    qnode.qnode_measures.reorder()
            session.flush()
            return qnodes

        def create_hierarchies(hsons, session):
            hierarchies = []
            for hson in hsons:
                hierarchy = model.Hierarchy(survey_id=survey_id)
                hierarchy.title = hson['title']
                hierarchy.description = hson['description']
                session.add(hierarchy)
                hierarchy.qnodes = create_qnodes(hson['qnodes'], session)
                hierarchy.qnodes.reorder()
            session.flush()
            return hierarchies

        with model.session_scope() as session:
            create_hierarchies(hsons, session)

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
