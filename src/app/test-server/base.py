import logging
import json
import os
import unittest
from unittest import mock

from sqlalchemy.sql import func
from tornado.escape import json_decode
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

import app
import model
from utils import denormalise


app.parse_options()


log = logging.getLogger('app.test_model')


def get_secure_cookie(user_email=None, super_email=None):
    def _get_secure_cookie(self, name):
        if name == 'user' and user_email is not None:
            with model.session_scope() as session:
                user = session.query(model.AppUser).\
                    filter(func.lower(model.AppUser.email) ==
                           func.lower(user_email)).one()
                return str(user.id).encode('utf8')
        elif name == 'superuser' and super_email is not None:
            with model.session_scope() as session:
                user = session.query(model.AppUser).\
                    filter(func.lower(model.AppUser.email) ==
                           func.lower(super_email)).one()
                return str(user.id).encode('utf8')
        else:
            return None

    return _get_secure_cookie


def mock_user(email):
    return mock.patch('tornado.web.RequestHandler.get_secure_cookie',
                get_secure_cookie(user_email=email))


class AqModelTestBase(unittest.TestCase):

    def setUp(self):
        super().setUp()
        engine = model.connect_db(os.environ.get('DATABASE_URL'))
        engine.execute("DROP SCHEMA IF EXISTS public CASCADE")
        engine.execute("DROP ROLE IF EXISTS analyst")
        engine.execute("CREATE SCHEMA public")
        model.initialise_schema(engine)
        model.connect_db_ro(os.environ.get('DATABASE_URL'))
        self.create_org_structure()
        self.create_survey_structure()

    def create_org_structure(self):
        engine = model.connect_db(os.environ.get('DATABASE_URL'))
        engine.execute("DROP SCHEMA IF EXISTS public CASCADE")
        engine.execute("DROP ROLE analyst")
        engine.execute("CREATE SCHEMA public")
        model.initialise_schema(engine)
        model.connect_db_ro(os.environ.get('DATABASE_URL'))

        with model.session_scope() as session:
            org1 = model.Organisation(
                name='Primary',
                url='http://primary.org',
                region="Nowhere",
                number_of_customers = 10)
            session.add(org1)
            session.flush()

            org2 = model.Organisation(
                name='Utility',
                url='http://utility.org',
                region="Somewhere",
                number_of_customers = 1000)
            session.add(org2)
            session.flush()

            user = model.AppUser(
                name='Admin', email='admin', role='admin',
                organisation_id=org1.id)
            user.set_password('foo')
            session.add(user)

            user = model.AppUser(
                name='Author', email='author', role='author',
                organisation_id=org1.id)
            user.set_password('bar')
            session.add(user)

            user = model.AppUser(
                name='Authority', email='authority', role='authority',
                organisation_id=org1.id)
            user.set_password('bar')
            session.add(user)

            user = model.AppUser(
                name='Consultant', email='consultant', role='consultant',
                organisation_id=org1.id)
            user.set_password('bar')
            session.add(user)

            user = model.AppUser(
                name='Org Admin', email='org_admin', role='org_admin',
                organisation_id=org2.id)
            user.set_password('bar')
            session.add(user)

            user = model.AppUser(
                name='Clerk', email='clerk', role='clerk',
                organisation_id=org2.id)
            user.set_password('bar')
            session.add(user)

    def create_survey_structure(self):
        proj_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..')

        with open(os.path.join(
                proj_dir, 'client', 'default_response_types.json')) as file:
            response_types = json.load(file)

        # Create survey
        with model.session_scope() as session:
            survey = entity = model.Survey(
                title='Test Survey 1',
                description="This is a test survey")
            survey.response_types = response_types
            session.add(survey)
            session.flush()
            survey_id = survey.id

        # Create measures
        msons = [
            {
                'title': "Foo Measure",
                'intent': "Foo",
                'weight': 100,
                'response_type': 'yes-no'
            },
            {
                'title': "Bar Measure",
                'intent': "Bar",
                'weight': 200,
                'response_type': 'yes-no'
            },
            {
                'title': "Baz Measure",
                'intent': "Baz",
                'weight': 300,
                'response_type': 'yes-no'
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
                            {
                                'title': "Process 2",
                                'description': "Test 2",
                                'measures': [2],
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

        def create_qnodes(qsons, session, hierarchy_id, parent_id=None):
            qnodes = []
            for qson in qsons:
                qnode = model.QuestionNode(
                    hierarchy_id=hierarchy_id,
                    parent_id=parent_id,
                    survey_id=survey_id)
                qnode.title = qson['title']
                qnode.description = qson['description']
                qnodes.append(qnode)
                session.add(qnode)
                session.flush()

                if 'children' in qson:
                    qnode.children = create_qnodes(
                        qson['children'], session, hierarchy_id,
                        parent_id=qnode.id)
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
                session.flush()
                hierarchy.qnodes = create_qnodes(
                    hson['qnodes'], session, hierarchy.id)
                hierarchy.qnodes.reorder()
            session.flush()
            return hierarchies

        with model.session_scope() as session:
            survey = session.query(model.Survey).first()
            create_hierarchies(hsons, session)
            survey.update_stats_descendants()


class AqHttpTestBase(AqModelTestBase, AsyncHTTPTestCase):

    def setUp(self):
        super().setUp()
        app.default_settings()

    def get_app(self):
        settings = app.get_minimal_settings().copy()
        settings['serve_traceback'] = True
        return Application(app.get_mappings(), **settings)

    def fetch(self, path, expected=None, decode=False, encoding='utf8', **kwargs):
        response = super().fetch(path, **kwargs)
        if response.code == 599:
            response.rethrow()
        if expected is not None:
            if encoding:
                body = response.body and response.body.decode(encoding) or ''
                self.assertEqual(
                    expected, response.code,
                    msg="{} failed: {}\n\n{}\n(body may be truncated)".format(
                        path, response.reason, body[:100]))
            else:
                body = response.body
                self.assertEqual(
                    expected, response.code,
                    msg="{} failed: {}\n".format(
                        path, response.reason))

        if decode:
            return denormalise(json_decode(response.body))
        else:
            return response
