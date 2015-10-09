import uuid
import json

import sqlalchemy
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import literal
from tornado import gen
from tornado.escape import json_decode, json_encode, utf8
import tornado.web

import handlers
import model
import logging

from utils import reorder, ToSon, truthy, updater


log = logging.getLogger('app.report_handler')


class DiffHandler(handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self):
        survey_id_a = self.get_argument("surveyId1", '')
        survey_id_b = self.get_argument("surveyId2", '')
        hierarchy_id = self.get_argument("hierarchyId", '')

        if survey_id_a == '':
            raise handlers.ModelError("Survey ID 1 required")
        if survey_id_b == '':
            raise handlers.ModelError("Survey ID 2 required")
        if hierarchy_id == '':
            raise handlers.ModelError("Hierarchy ID required")

        with model.session_scope() as session:
            diff_engine = DiffEngine(session, survey_id_a, survey_id_b, hierarchy_id)
            son = {
                'diff': diff_engine.execute()
            }

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()


class DiffEngine:
    def __init__(self, session, survey_id_a, survey_id_b, hierarchy_id):
        self.session = session
        self.survey_id_a = survey_id_a
        self.survey_id_b = survey_id_b
        self.hierarchy_id = hierarchy_id

    def execute(self):
        qnode_pairs = self.get_qnodes()
        measure_pairs = self.get_measures()

        to_son = ToSon(include=[
            r'/id$',
            r'/parent_id$',
            r'/title$',
            r'/description$',
            r'/intent$',
            r'/inputs$',
            r'/scenario$',
            r'/questions$',
            r'/weight$',
            r'/seq$',
            # Descend
            r'/[0-9]+$',
            r'^/[0-9]+/[^/]+$',
        ])

        qnode_diff = [{
                'type': 'qnode',
                'tags': [],
                'pair': pair,
            } for pair in to_son(qnode_pairs)]
        self.add_qnode_metadata(qnode_pairs, qnode_diff)
        self.remove_unchanged_fields(qnode_diff)

        measure_diff = [{
                'type': 'measure',
                'tags': [],
                'pair': pair,
            } for pair in to_son(measure_pairs)]
        self.add_measure_metadata(measure_pairs, measure_diff)
        self.remove_unchanged_fields(measure_diff)

        diff = qnode_diff + measure_diff

        def path_key(diff_item):
            a, b = diff_item['pair']
            if a and b:
                return 0, b['path'].split('.')
            elif b:
                return 0, b['path'].split('.')
            elif a:
                return 1, a['path'].split('.')
            else:
                return 2
        diff.sort(key=path_key)

        return diff

    def get_qnodes(self):
        QA = model.QuestionNode
        QB = aliased(model.QuestionNode, name='qnode_b')

        # Find modified / relocated qnodes
        qnode_mod_query = (self.session.query(QA, QB)
            .join(QB, QA.id == QB.id)

            # Basic survey membership
            .filter(QA.survey_id == self.survey_id_a,
                    QB.survey_id == self.survey_id_b,
                    QA.hierarchy_id == self.hierarchy_id,
                    QB.hierarchy_id == self.hierarchy_id)

            # Filter for modified objects
            .filter((QA.title != QB.title) |
                    (QA.description != QB.description) |
                    (QA.parent_id != QB.parent_id) |
                    (QA.seq != QB.seq))
        )

        # Find deleted qnodes
        qnode_del_query = (self.session.query(QA, literal(None))
            .select_from(QA)
            .filter(QA.survey_id == self.survey_id_a,
                    QA.hierarchy_id == self.hierarchy_id,
                    ~QA.id.in_(
                        self.session.query(QB.id)
                            .filter(QB.survey_id == self.survey_id_b,
                                    QB.hierarchy_id == self.hierarchy_id)))
        )

        # Find added qnodes
        qnode_add_query = (self.session.query(literal(None), QB)
            .select_from(QB)
            .filter(QB.survey_id == self.survey_id_b,
                    QB.hierarchy_id == self.hierarchy_id,
                    ~QB.id.in_(
                        self.session.query(QA.id)
                            .filter(QA.survey_id == self.survey_id_a,
                                    QA.hierarchy_id == self.hierarchy_id)))
        )

        return list(qnode_mod_query.all()
                    + qnode_add_query.all()
                    + qnode_del_query.all())

    def get_measures(self):
        QA = model.QuestionNode
        QB = aliased(model.QuestionNode, name='qnode_b')
        MA = model.Measure
        MB = aliased(model.Measure, name='measure_b')
        QMA = model.QnodeMeasure
        QMB = aliased(model.QnodeMeasure, name='qnode_measure_link_b')

        # Find modified / relocated measures
        measure_mod_query = (self.session.query(MA, MB)

            .join(MB, MA.id == MB.id)

            .join(QMA,
                  (QMA.survey_id == MA.survey_id) &
                  (QMA.measure_id == MA.id))
            .join(QMB,
                  (QMB.survey_id == MB.survey_id) &
                  (QMB.measure_id == MB.id))
            .join(QA,
                  (QMA.survey_id == QA.survey_id) &
                  (QMA.qnode_id == QA.id))
            .join(QB,
                  (QMB.survey_id == QB.survey_id) &
                  (QMB.qnode_id == QB.id))

            # Basic survey membership
            .filter(QA.survey_id == self.survey_id_a,
                    QB.survey_id == self.survey_id_b,
                    QA.hierarchy_id == self.hierarchy_id,
                    QB.hierarchy_id == self.hierarchy_id)

            # Filter for modified objects
            .filter((MA.title != MB.title) |
                    (MA.intent != MB.intent) |
                    (MA.inputs != MB.inputs) |
                    (MA.scenario != MB.scenario) |
                    (MA.questions != MB.questions) |
                    (MA.response_type != MB.response_type) |
                    (MA.weight != MB.weight) |
                    (QMA.qnode_id != QMB.qnode_id) |
                    (QMA.seq != QMB.seq))
        )

        ncols = len(MA.__table__.c)

        # Find deleted measures
        measure_del_query = (self.session.query(MA, literal(None))
            .select_from(MA)
            .join(QMA,
                  (QMA.survey_id == MA.survey_id) &
                  (QMA.measure_id == MA.id))
            .join(QA,
                  (QMA.survey_id == QA.survey_id) &
                  (QMA.qnode_id == QA.id))
            .filter(QA.survey_id == self.survey_id_a,
                    QA.hierarchy_id == self.hierarchy_id,
                    ~QMA.measure_id.in_(
                        self.session.query(QMB.measure_id)
                            .join(QB,
                                  (QMB.survey_id == QB.survey_id) &
                                  (QMB.qnode_id == QB.id))
                            .filter(QB.survey_id == self.survey_id_b,
                                    QB.hierarchy_id == self.hierarchy_id)))
        )

        # Find added measures
        measure_add_query = (self.session.query(literal(None), MB)
            .select_from(MB)
            .join(QMB,
                  (QMB.survey_id == MB.survey_id) &
                  (QMB.measure_id == MB.id))
            .join(QB,
                  (QMB.survey_id == QB.survey_id) &
                  (QMB.qnode_id == QB.id))
            .filter(QB.survey_id == self.survey_id_b,
                    QB.hierarchy_id == self.hierarchy_id,
                    ~QMB.measure_id.in_(
                        self.session.query(QMA.measure_id)
                            .join(QA,
                                  (QMA.survey_id == QA.survey_id) &
                                  (QMA.qnode_id == QA.id))
                            .filter(QA.survey_id == self.survey_id_a,
                                    QA.hierarchy_id == self.hierarchy_id)))
        )

        return list(measure_mod_query.all()
                    + measure_add_query.all()
                    + measure_del_query.all())

    def add_qnode_metadata(self, qnode_pairs, qnode_diff):
        for (a, b), diff_item in zip(qnode_pairs, qnode_diff):
            a_son, b_son = diff_item['pair']
            if a:
                a_son['path'] = a.get_path()
            if b:
                b_son['path'] = b.get_path()

    def add_measure_metadata(self, measure_pairs, measure_diff):
        for (a, b), diff_item in zip(measure_pairs, measure_diff):
            a_son, b_son = diff_item['pair']
            if a:
                a_son['path'] = a.get_path(self.hierarchy_id)
                a_son['parentId'] = str(a.get_parent(self.hierarchy_id).id)
            if b:
                b_son['path'] = b.get_path(self.hierarchy_id)
                b_son['parentId'] = str(b.get_parent(self.hierarchy_id).id)

    def remove_unchanged_fields(self, diff, ignore=None):
        if ignore is None:
            ignore = {'id', 'parentId', 'path', 'title', 'type'}
        for diff_item in diff:
            a, b = diff_item['pair']
            keys = a is not None and a.keys() or b.keys()
            changes = 0
            for name in list(keys):
                if name in ignore:
                    continue
                if a is None:
                    del b[name]
                elif b is None:
                    del a[name]
                elif a[name] == b[name]:
                    del a[name]
                    del b[name]
                else:
                    changes += 1
            if changes > 0:
                diff_item['tags'].append('modified')
