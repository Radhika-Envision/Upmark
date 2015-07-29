import os
from unittest import mock
import urllib

from sqlalchemy.sql import func

import model
from utils import to_dict, simplify, normalise, truthy
import unittest


class SurveyStructureIntegrationTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        engine = model.connect_db(os.environ.get('DATABASE_URL'))
        engine.execute("DROP SCHEMA IF EXISTS public CASCADE")
        engine.execute("CREATE SCHEMA public")
        model.initialise_schema(engine)

    def test_1_create_survey(self):
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
                    qnode.measures.reorder()
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
