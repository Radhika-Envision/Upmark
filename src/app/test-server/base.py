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


def print_hierarchy(hierarchy):

    def print_measure(qnode_measure, indent=""):
        print("{}{}".format(indent, qnode_measure.measure))
        indent += "  "
        print("{}seq: {}".format(indent, qnode_measure.seq))
        print("{}weight: {}".format(indent, qnode_measure.measure.weight))

    def print_qnode(qnode, indent=""):
        print("{}{}".format(indent, qnode))
        indent += "  "
        print("{}seq: {}".format(indent, qnode.seq))
        print("{}total_weight: {}".format(indent, qnode.total_weight))
        for c in qnode.children:
            print_qnode(c, indent)
        for m in qnode.qnode_measures:
            print_measure(m, indent)

    print(hierarchy)
    for qnode in hierarchy.qnodes:
        print_qnode(qnode, indent="  ")


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
                locations=[model.OrgLocation(
                    description="Nowhere", region="Nowhere")],
                meta=model.OrgMeta(asset_types=['water wholesale']))
            session.add(org1)

            org2 = model.Organisation(
                name='Utility',
                url='http://utility.org',
                locations=[model.OrgLocation(
                    description="Somewhere", region="Somewhere")],
                meta=model.OrgMeta(asset_types=['water local']))
            session.add(org2)

            user = model.AppUser(
                name='Admin', email='admin', role='admin',
                organisation=org1)
            user.set_password('foo')
            session.add(user)

            user = model.AppUser(
                name='Author', email='author', role='author',
                organisation=org1, email_interval=model.ONE_DAY_S)
            user.set_password('bar')
            session.add(user)

            user = model.AppUser(
                name='Authority', email='authority', role='authority',
                organisation=org1)
            user.set_password('bar')
            session.add(user)

            user = model.AppUser(
                name='Consultant', email='consultant', role='consultant',
                organisation=org1)
            user.set_password('bar')
            session.add(user)

            user = model.AppUser(
                name='Org Admin', email='org_admin', role='org_admin',
                organisation=org2)
            user.set_password('bar')
            session.add(user)

            user = model.AppUser(
                name='Clerk', email='clerk', role='clerk',
                organisation=org2)
            user.set_password('bar')
            session.add(user)

    def create_survey_structure(self):
        proj_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..')

        with open(os.path.join(
                proj_dir, 'client', 'default_response_types.json')) as file:
            response_types = json.load(file)

        # Measure declaration, separate from hierarchy to allow cross-linking
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
            {
                'title': "Unreferenced Measure 1",
                'intent': "Deleted",
                'weight': 300,
                'response_type': 'yes-no'
            },
            {
                'title': "Unreferenced Measure 2",
                'intent': "Deleted",
                'weight': 600,
                'response_type': 'yes-no'
            },
        ]

        # Hierarchy declaration, with qnodes and measures as descendants
        hsons = [
            {
                'title': "Hierarchy 1",
                'description': "Test",
                'qnodes': [
                    {
                        'title': "Function 0",
                        'description': "deleted",
                        'deleted': True,
                    },
                    {
                        'title': "Function 1",
                        'description': "Test",
                        'children': [
                            {
                                'title': "Process 1.0",
                                'description': "deleted",
                                'measures': [],
                                'deleted': True,
                            },
                            {
                                'title': "Process 1.1",
                                'description': "Test",
                                'measures': [0, 1],
                            },
                            {
                                'title': "Process 1.2",
                                'description': "Test 2",
                                'measures': [2],
                            },
                            {
                                'title': "Process 1.3",
                                'description': "deleted",
                                'measures': [3],
                                'deleted': True,
                            },
                        ],
                    },
                    {
                        'title': "Function 2",
                        'description': "Test",
                    },
                    {
                        'title': "Function 3",
                        'description': "deleted",
                        'deleted': True,
                        'children': [
                            {
                                'title': "Process 3.1",
                                'description': "deleted parent",
                                'measures': [4],
                            },
                            {
                                'title': "Process 3.2",
                                'description': "deleted parent",
                                'measures': [],
                            },
                        ],
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
            {
                'title': "Hierarchy 3",
                'description': "Test",
                'deleted': True,
                'qnodes': [
                    {
                        'title': "Division 1",
                        'description': "Test",
                        'children': [
                            {
                                'title': "Division 1",
                                'description': "Test",
                                'measures': [1, 2],
                            },
                        ],
                    },
                    {
                        'title': "Division 2",
                        'description': "Test",
                    },
                ],
            },
        ]

        with model.session_scope() as session:
            # Create survey
            survey = entity = model.Survey(
                title='Test Survey 1',
                description="This is a test survey")
            survey.response_types = response_types
            session.add(survey)

            # Create measures
            all_measures = []
            for mson in msons:
                measure = model.Measure(survey=survey, **mson)
                session.add(measure)
                all_measures.append(measure)
            survey.measures = all_measures

            # Create hierarchy and qnodes
            def create_qnodes(qsons, hierarchy, parent=None):
                qnodes = []
                for qson in qsons:
                    qnode = model.QuestionNode(
                        hierarchy=hierarchy,
                        parent=parent,
                        survey=survey,
                        title=qson['title'],
                        description=qson['description'],
                        deleted=qson.get('deleted', False))
                    session.add(qnode)

                    # Explicitly add to collection because backref is one-way.
                    if not qson.get('deleted', False):
                        qnodes.append(qnode)

                    if 'children' in qson:
                        qnode.children = create_qnodes(
                            qson['children'], hierarchy, parent=qnode)
                        qnode.children.reorder()

                    qnode.measures = [all_measures[i]
                                      for i in qson.get('measures', [])]
                    qnode.qnode_measures.reorder()
                return qnodes

            def create_hierarchies(hsons):
                hierarchies = []
                for hson in hsons:
                    hierarchy = model.Hierarchy(
                        survey=survey,
                        title=hson['title'],
                        description=hson['description'],
                        deleted=hson.get('deleted', False))
                    session.add(hierarchy)

                    # Explicitly add to collection because backref is one-way.
                    if not hson.get('deleted', False):
                        survey.hierarchies.append(hierarchy)

                    hierarchy.qnodes = create_qnodes(
                        hson['qnodes'], hierarchy)
                    hierarchy.qnodes.reorder()
                return hierarchies

            create_hierarchies(hsons)
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
