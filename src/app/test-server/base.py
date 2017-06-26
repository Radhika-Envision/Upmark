import logging
import json
import os
import unittest
from unittest import mock

from sqlalchemy.sql import func
from tornado.escape import json_decode, json_encode
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

import app
import model
from score import Calculator
from utils import denormalise


app.parse_options()


log = logging.getLogger('app.test.test_model')


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


def print_survey(survey):

    def print_measure(qnode_measure, indent=""):
        print("{}{}".format(indent, qnode_measure.measure))
        indent += "  "
        if qnode_measure.error:
            print("{}error: {}".format(indent, qnode_measure.error))
        print("{}seq: {}".format(indent, qnode_measure.seq))
        print("{}weight: {}".format(indent, qnode_measure.measure.weight))

    def print_qnode(qnode, indent=""):
        print("{}{}".format(indent, qnode))
        indent += "  "
        if qnode.error:
            print("{}error: {}".format(indent, qnode.error))
        print("{}seq: {}".format(indent, qnode.seq))
        print("{}total_weight: {}".format(indent, qnode.total_weight))
        print("{}n_measures: {}".format(indent, qnode.n_measures))
        for c in qnode.children:
            print_qnode(c, indent)
        for m in qnode.qnode_measures:
            print_measure(m, indent)

    print(survey)
    if survey.error:
        print("  error: ", survey.error)
    for qnode in survey.qnodes:
        print_qnode(qnode, indent="  ")


class AqModelTestBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._engine = model.connect_db(os.environ.get('DATABASE_URL'))

    def setUp(self):
        super().setUp()
        engine = self.__class__._engine
        engine.execute("DROP SCHEMA IF EXISTS public CASCADE")
        engine.execute("DROP ROLE IF EXISTS analyst")
        engine.execute("CREATE SCHEMA public")
        model.initialise_schema(engine)
        model.connect_db_ro(os.environ.get('DATABASE_URL'))
        self.create_org_structure()
        self.create_program_structure()

    def create_org_structure(self):
        engine = self.__class__._engine
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
                organisation=org1, password='foo')
            session.add(user)

            user = model.AppUser(
                name='Author', email='author', role='author',
                organisation=org1, password='bar')
            session.add(user)

            user = model.AppUser(
                name='Authority', email='authority', role='authority',
                organisation=org1, password='bar')
            session.add(user)

            user = model.AppUser(
                name='Consultant', email='consultant', role='consultant',
                organisation=org1, password='bar')
            session.add(user)

            user = model.AppUser(
                name='Org Admin', email='org_admin', role='org_admin',
                organisation=org2, password='bar')
            session.add(user)

            user = model.AppUser(
                name='Clerk', email='clerk', role='clerk',
                organisation=org2, password='bar')
            session.add(user)

    def create_program_structure(self):
        proj_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..')

        with open(os.path.join(
                proj_dir, 'test-server', 'default_response_types.json')) as file:
            response_types = json.load(file)

        # Measure declaration, separate from survey to allow cross-linking.
        # Weights are chosen so that each combination gives a different sum.
        msons = [
            {
                'title': "Foo Measure",
                'description': "Yes / No",
                'weight': 3,
                'response_type': 'Yes / No'
            },
            {
                'title': "Bar Measure",
                'description': "Numerical",
                'weight': 6,
                'response_type': 'Numerical'
            },
            {
                'title': "Baz Measure",
                'description': "Planned (might have dependants)",
                'weight': 11,
                'response_type': 'Planned'
            },
            {
                'title': "Qux Measure",
                'description': "Actual (should have a dependency)",
                'weight': 13,
                'response_type': 'Actual'
            },
            {
                'title': "Unreferenced Measure 1",
                'description': "Deleted",
                'weight': 17,
                'response_type': 'Yes / No'
            },
            {
                'title': "Unreferenced Measure 2",
                'description': "Deleted",
                'weight': 19,
                'response_type': 'Yes / No'
            },
        ]

        # Survey declaration, with qnodes and measures as descendants
        hsons = [
            {
                'title': "Survey 1",
                'description': "Test",
                'structure': {
                    'levels': [
                        {
                            'title': 'Functions',
                            'label': 'F',
                            'has_measures': False
                        },
                        {
                            'title': 'Processes',
                            'label': 'P',
                            'has_measures': True
                        },
                    ],
                    'measure': {
                        'title': 'Measures',
                        'label': 'M'
                    }
                },
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
                                'measures': [2, 3],
                            },
                            {
                                'title': "Process 1.3",
                                'description': "deleted",
                                'measures': [4],
                                'deleted': True,
                            },
                        ],
                    },
                    {
                        'title': "Function 2",
                        'description': "Empty category",
                    },
                    {
                        'title': "Function 3",
                        'description': "deleted",
                        'deleted': True,
                        'children': [
                            {
                                'title': "Process 3.1",
                                'description': "deleted parent",
                                'measures': [5],
                            },
                            {
                                'title': "Process 3.2",
                                'description': "deleted parent",
                                'measures': [],
                            },
                        ],
                    },
                ],
                'dependencies': [(2, 'planned', 3, 'planned')],
            },
            {
                'title': "Survey 2",
                'description': "Test",
                'structure': {
                    'levels': [
                        {
                            'title': 'Sections',
                            'label': 'S',
                            'has_measures': False
                        },
                        {
                            'title': 'Sub-Sections',
                            'label': 'Ss',
                            'has_measures': True
                        },
                    ],
                    'measure': {
                        'title': 'Measures',
                        'label': 'M'
                    }
                },
                'qnodes': [
                    {
                        'title': "Section 1",
                        'description': "Test",
                        'children': [
                            {
                                'title': "SubSection 1.1",
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
                'title': "Survey 3",
                'description': "Test",
                'deleted': True,
                'structure': {
                    'levels': [
                        {
                            'title': 'Divisions',
                            'label': 'D',
                            'has_measures': False
                        },
                        {
                            'title': 'Sub-Divisions',
                            'label': 'Sd',
                            'has_measures': True
                        },
                    ],
                    'measure': {
                        'title': 'Measures',
                        'label': 'M'
                    }
                },
                'qnodes': [
                    {
                        'title': "Division 1",
                        'description': "Test",
                        'children': [
                            {
                                'title': "Sub-Division 1.1",
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
            program = entity = model.Program(
                title='Test Program 1',
                description="This is a test program")
            session.add(program)

            # Create response types
            rts = {}
            for rt_def in response_types:
                rt = model.ResponseType(program=program, **rt_def)
                rts[rt_def['name']] = rt
                session.add(rt)

            # Create measures
            ordered_measures = []
            for mson in msons:
                mson_clean = mson.copy()
                del mson_clean['response_type']
                measure = model.Measure(program=program, **mson_clean)
                measure.response_type = rts[mson['response_type']]
                session.add(measure)
                ordered_measures.append(measure)
            # Note that program.measures is unordered so can't be accessed by
            # index
            program.measures = ordered_measures
            # Ensure measures have IDs
            session.flush()

            # Create qnodes
            def create_qnodes(qsons, survey, parent=None):
                qnodes = []
                for qson in qsons:
                    qnode = model.QuestionNode(
                        survey=survey,
                        parent=parent,
                        program=program,
                        title=qson['title'],
                        seq=-1,
                        description=qson['description'],
                        deleted=qson.get('deleted', False))
                    session.add(qnode)

                    # Explicitly add to collection because backref is one-way.
                    if not qson.get('deleted', False):
                        qnodes.append(qnode)

                    if 'children' in qson:
                        qnode.children = create_qnodes(
                            qson['children'], survey, parent=qnode)
                        qnode.children.reorder()

                    msons = qson.get('measures', [])
                    for measure in (ordered_measures[i] for i in msons):
                        qm = model.QnodeMeasure(
                            program=program, survey=survey,
                            qnode=qnode, measure=measure,
                            seq=-1)
                    qnode.qnode_measures.reorder()
                return qnodes

            def link_measures(survey, deps):
                for source_i, source_field, target_i, target_field in deps:
                    source_measure = ordered_measures[source_i]
                    target_measure = ordered_measures[target_i]

                    mv = model.MeasureVariable(
                        program=program,
                        survey=survey,
                        source_measure_id=source_measure.id,
                        source_field=source_field,
                        target_measure_id=target_measure.id,
                        target_field=target_field)
                    session.add(mv)

            # Create survey
            def create_surveys(hsons):
                surveys = []
                for hson in hsons:
                    survey = model.Survey(
                        program=program,
                        title=hson['title'],
                        description=hson['description'],
                        deleted=hson.get('deleted', False))
                    survey.structure = hson['structure']
                    session.add(survey)

                    # Explicitly add to collection because backref is one-way.
                    if not hson.get('deleted', False):
                        program.surveys.append(survey)

                    survey.qnodes = create_qnodes(
                        hson['qnodes'], survey)
                    survey.qnodes.reorder()

                    if 'dependencies' in hson:
                        link_measures(survey, hson['dependencies'])

                    calculator = Calculator.structural()
                    calculator.mark_entire_survey_dirty(survey)
                    calculator.execute()
                    # print_survey(survey)
                return surveys

            create_surveys(hsons)


def printable(mime_type):
    if 'text/' in mime_type:
        return True
    if '/xml' in mime_type or '+xml' in mime_type:
        return True
    if 'application/json' in mime_type:
        return True


class AqHttpTestBase(AqModelTestBase, AsyncHTTPTestCase):

    def setUp(self):
        super().setUp()
        app.default_settings()

    def get_app(self):
        settings = app.get_minimal_settings().copy()
        settings['serve_traceback'] = True
        return Application(app.get_mappings(), **settings)

    def fetch(self, path, expected=None, decode=False, **kwargs):
        log.debug("%s %s", kwargs.get('method'), path)
        if 'body' in kwargs and not isinstance(kwargs['body'], (str, bytes)):
            kwargs['body'] = json_encode(kwargs['body'])
        response = super().fetch(path, **kwargs)
        if response.code == 599:
            response.rethrow()
        if expected is not None:
            if printable(response.headers["Content-Type"]):
                body = '\n\n' + response.body.decode('utf-8')
                if len(body) > 10000:
                    body = body[:9900] + '\n(body is truncated)'
            else:
                body = '\n\n(non-text)'
            self.assertEqual(
                expected, response.code,
                msg="{} {}\nReason: {}{}".format(
                    kwargs.get('method'), path, response.reason, body))

        if decode:
            return denormalise(json_decode(response.body))
        else:
            return response
