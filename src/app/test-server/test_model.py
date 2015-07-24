import os
from unittest import mock
import urllib

from sqlalchemy.sql import func

import model
from utils import to_dict, simplify, normalise, truthy
import unittest


class SurveyStructureTestCase(unittest.TestCase):

    def create_survey_structure(self):
        engine = model.connect_db(os.environ.get('DATABASE_URL'))
        model.Base.metadata.drop_all(engine)
        model.initialise_schema(engine)

        with model.session_scope() as session:
            survey1 = entity = model.Survey(
                title='Test Survey 1',
                description="This is a test survey")
            session.add(entity)
            session.flush()

            h1 = entity = model.Hierarchy(
                title='Test Hierarchy 1',
                description="Test")
            entity.survey = survey1
            session.add(entity)
            session.flush()

            h2 = entity = model.Hierarchy(
                title='Test Hierarchy 2',
                description="Test")
            entity.survey = survey1
            session.add(entity)
            session.flush()

            qnode_h1_1 = entity = model.QuestionNode(
                title='Function 1',
                description="Test")
            entity.survey = survey1
            h1.qnodes.append(entity)
            session.add(entity)
            session.flush()

            qnode_h1_2 = entity = model.QuestionNode(
                title='Function 2',
                description="Test")
            entity.survey = survey1
            h1.qnodes.append(entity)
            session.add(entity)
            session.flush()

    def setUp(self):
        super().setUp()
        self.create_survey_structure()

    def test_create_structure(self):
        return

        # TODO: automate survey construction so it's easier to read in this test.
        measure_son = [
            {
                'title': "Foo Measure",
                'intent': "Foo",
                'weight': 100,
            },
            {
                'title': "Bar Measure",
                'intent': "Bar",
                'weight': 200,
            },
            {
                'title': "Baz Measure",
                'intent': "Baz",
                'weight': 300,
            },
        ]

        survey_son = {
            'title': "Test survey 1",
            'description': "Test",
            'hierarchies': [
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
                                    'measures': measure_son[1:],
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
                                    'measures': measure_son[:-1],
                                },
                            ],
                        },
                        {
                            'title': "Section 2",
                            'description': "Test",
                        },
                    ],
                },
            ],
        }
