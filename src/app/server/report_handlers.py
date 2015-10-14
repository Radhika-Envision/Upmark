import csv
import json
import os
import tempfile
import uuid

import sqlalchemy
from sqlalchemy import String
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import cast, literal
import sqlparse
from tornado import gen
from tornado.escape import json_decode, json_encode, utf8, to_basestring
from tornado import gen
import tornado.web
from tornado.concurrent import run_on_executor
from concurrent.futures import ThreadPoolExecutor

import handlers
import model
import logging

from utils import falsy, ToSon, truthy


log = logging.getLogger('app.report_handler')


class DiffHandler(handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self):
        survey_id_a = self.get_argument("surveyId1", '')
        survey_id_b = self.get_argument("surveyId2", '')
        hierarchy_id = self.get_argument("hierarchyId", '')

        ignore_tags = set().union(self.get_arguments("ignoreTag"))

        if survey_id_a == '':
            raise handlers.ModelError("Survey ID 1 required")
        if survey_id_b == '':
            raise handlers.ModelError("Survey ID 2 required")
        if hierarchy_id == '':
            raise handlers.ModelError("Hierarchy ID required")

        with model.session_scope() as session:
            diff_engine = DiffEngine(session, survey_id_a, survey_id_b, hierarchy_id)
            diff = diff_engine.execute()
            diff = [di for di in diff
                    if len(set().union(di['tags']).difference(ignore_tags)) > 0]
            son = {
                'diff': diff
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
            r'/response_type$',
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
        self.add_metadata(qnode_pairs, qnode_diff)
        self.remove_unchanged_fields(qnode_diff)

        measure_diff = [{
                'type': 'measure',
                'tags': [],
                'pair': pair,
            } for pair in to_son(measure_pairs)]
        self.add_measure_metadata(measure_pairs, measure_diff)
        self.add_metadata(measure_pairs, measure_diff)
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

        HA = model.Hierarchy
        HB = aliased(model.Hierarchy, name='hierarchy_b')
        hierarchy_a, hierarchy_b = (self.session.query(HA, HB)
            .join(HB, (HA.id == HB.id))
            .filter(HA.survey_id == self.survey_id_a,
                    HB.survey_id == self.survey_id_b,
                    HA.id == self.hierarchy_id)
            .first())
        to_son = ToSon(include=[
            r'/id$',
            r'/title$',
            r'/description$'
        ])
        top_level_diff = [
            {
                'type': 'survey',
                'tags': ['context'],
                'pair': [to_son(hierarchy_a.survey), to_son(hierarchy_b.survey)]
            },
            {
                'type': 'hierarchy',
                'tags': ['context'],
                'pair': [to_son(hierarchy_a), to_son(hierarchy_b)]
            }
        ]
        self.remove_unchanged_fields(top_level_diff)

        return top_level_diff + diff

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
        # Create sets of ids; group by transform type
        deleted = {str(a.id) for a, b in qnode_pairs if b is None}
        added = {str(b.id) for a, b in qnode_pairs if a is None}
        relocated = {str(a.id) for a, b in qnode_pairs
                     if a and b and a.parent_id != b.parent_id}
        item_index = {str(a.id) for a, b in qnode_pairs
                      if a and b and a.seq != b.seq}

        reorder_ignore = set().union(deleted, added, relocated)

        for (a, b), diff_item in zip(qnode_pairs, qnode_diff):
            a_son, b_son = diff_item['pair']
            if a:
                a_son['path'] = a.get_path()
            if b:
                b_son['path'] = b.get_path()
            if a and b and str(a.parent_id) == str(b.parent_id):
                if self.qnode_was_reordered(a, b, reorder_ignore):
                   diff_item['tags'].append('reordered')

    def add_measure_metadata(self, measure_pairs, measure_diff):
        # Create sets of ids; group by transform type
        deleted = {str(a.id) for a, b in measure_pairs if b is None}
        added = {str(b.id) for a, b in measure_pairs if a is None}
        relocated = {str(a.id) for a, b in measure_pairs
                     if a and b and (a.get_parent(self.hierarchy_id).id !=
                                     b.get_parent(self.hierarchy_id).id)}
        item_index = {str(a.id) for a, b in measure_pairs
                      if a and b and (a.get_seq(self.hierarchy_id) !=
                                      b.get_seq(self.hierarchy_id))}

        reorder_ignore = set().union(deleted, added, relocated)

        for (a, b), diff_item in zip(measure_pairs, measure_diff):
            a_son, b_son = diff_item['pair']
            if a:
                a_son['path'] = a.get_path(self.hierarchy_id)
                a_son['parentId'] = str(a.get_parent(self.hierarchy_id).id)
                a_son['seq'] = a.get_seq(self.hierarchy_id)
            if b:
                b_son['path'] = b.get_path(self.hierarchy_id)
                b_son['parentId'] = str(b.get_parent(self.hierarchy_id).id)
                b_son['seq'] = b.get_seq(self.hierarchy_id)
            if a and b and a_son['parentId'] == b_son['parentId']:
                if self.measure_was_reordered(a, b, reorder_ignore):
                   diff_item['tags'].append('reordered')

    def qnode_was_reordered(self, a, b, reorder_ignore):
        a_siblings = (self.session.query(model.QuestionNode.id)
            .filter(model.QuestionNode.parent_id == a.parent_id,
                    model.QuestionNode.survey_id == self.survey_id_a,
                    ~model.QuestionNode.id.in_(reorder_ignore))
            .order_by(model.QuestionNode.seq)
            .all())
        b_siblings = (self.session.query(model.QuestionNode.id)
            .filter(model.QuestionNode.parent_id == b.parent_id,
                    model.QuestionNode.survey_id == self.survey_id_b,
                    ~model.QuestionNode.id.in_(reorder_ignore))
            .order_by(model.QuestionNode.seq)
            .all())
        a_siblings = [str(id_) for (id_,) in a_siblings]
        b_siblings = [str(id_) for (id_,) in b_siblings]
        if not str(a.id) in a_siblings or not str(b.id) in b_siblings:
            return False
        a_index = a_siblings.index(str(a.id))
        a_siblings = a_siblings[max(a_index - 1, 0):
                                min(a_index + 1, len(a_siblings))]
        b_index = b_siblings.index(str(b.id))
        b_siblings = b_siblings[max(b_index - 1, 0):
                                min(b_index + 1, len(b_siblings))]
        return a_siblings != b_siblings

    def measure_was_reordered(self, a, b, reorder_ignore):
        a_parent = a.get_parent(self.hierarchy_id)
        b_parent = b.get_parent(self.hierarchy_id)
        a_siblings = (self.session.query(model.Measure.id)
            .join(model.QnodeMeasure,
                  (model.QnodeMeasure.survey_id == model.Measure.survey_id) &
                  (model.QnodeMeasure.measure_id == model.Measure.id))
            .filter(model.QnodeMeasure.qnode_id == a_parent.id,
                    model.QnodeMeasure.survey_id == self.survey_id_a,
                    ~model.Measure.id.in_(reorder_ignore))
            .order_by(model.QnodeMeasure.seq)
            .all())
        b_siblings = (self.session.query(model.Measure.id)
            .join(model.QnodeMeasure,
                  (model.QnodeMeasure.survey_id == model.Measure.survey_id) &
                  (model.QnodeMeasure.measure_id == model.Measure.id))
            .filter(model.QnodeMeasure.qnode_id == b_parent.id,
                    model.QnodeMeasure.survey_id == self.survey_id_b,
                    ~model.Measure.id.in_(reorder_ignore))
            .order_by(model.QnodeMeasure.seq)
            .all())

        a_siblings = [str(id_) for (id_,) in a_siblings]
        b_siblings = [str(id_) for (id_,) in b_siblings]
        #log.error('Siblings A %s', a_siblings)
        #log.error('Siblings B %s', b_siblings)
        if not str(a.id) in a_siblings or not str(b.id) in b_siblings:
            return False
        a_index = a_siblings.index(str(a.id))
        a_siblings = a_siblings[max(a_index - 1, 0):
                                min(a_index + 1, len(a_siblings))]
        b_index = b_siblings.index(str(b.id))
        b_siblings = b_siblings[max(b_index - 1, 0):
                                min(b_index + 1, len(b_siblings))]
        return a_siblings != b_siblings

    def add_metadata(self, pairs, diff):
        for (a, b), diff_item in zip(pairs, diff):
            a_son, b_son = diff_item['pair']
            if a and b:
                if a_son['parentId'] != b_son['parentId']:
                    diff_item['tags'].append('relocated')
                elif a_son['seq'] != b_son['seq']:
                    diff_item['tags'].append('list index')
            elif a and not b:
                diff_item['tags'].append('deleted')
            elif b and not a:
                diff_item['tags'].append('added')

    def remove_unchanged_fields(self, diff, ignore=None, protect=None):
        if protect is None:
            protect = {'id', 'parentId', 'title', 'path'}
        if ignore is None:
            ignore = {'id', 'parentId', 'path', 'seq'}
        for diff_item in diff:
            a, b = diff_item['pair']
            keys = a is not None and a.keys() or b.keys()
            changes = 0
            for name in list(keys):
                changed = a and b and a[name] != b[name]
                if not changed and not name in protect:
                    if a:
                        del a[name]
                    if b:
                        del b[name]
                if changed and not name in ignore:
                    changes += 1
            if changes > 0:
                diff_item['tags'].append('modified')


class AdHocHandler(handlers.Paginate, handlers.BaseHandler):
    '''
    Allows ad-hoc queries using SQL.
    '''

    executor = ThreadPoolExecutor(max_workers=4)

    TYPES = {
        2950: 'UUID',
        25: 'text',
        1114: 'datetime',
        23: 'integer'
    }
    CHUNKSIZE = 100
    MAX_LIMIT = 2000
    BUF_SIZE = 4096

    @handlers.authz('consultant')
    @gen.coroutine
    def post(self, file_type):
        query = to_basestring(self.request.body)
        limit = int(self.get_argument('limit', AdHocHandler.MAX_LIMIT))
        if limit > AdHocHandler.MAX_LIMIT:
            raise handlers.ModelError(
                'Limit is too high. Max %d' % AdHocHandler.MAX_LIMIT)

        if file_type == 'json':
            yield self.as_json(query, limit)
        elif file_type == 'csv':
            yield self.as_csv(query, limit)
        elif file_type == 'xlsx':
            yield self.as_xlsx(query, limit)
        else:
            raise handlers.MissingDocError('%s not supported' % file_type)

    @run_on_executor
    def export_json(self, path, query, limit):
        with model.session_scope() as session, open(path, 'w') as f:
            result = session.execute(query)
            cols = [{
                    'name': c.name,
                    'type': AdHocHandler.TYPES.get(c.type_code, None)
                } for c in result.context.cursor.description]

            f.write('{"cols": %s, "rows": [' % json_encode(cols))
            first = True
            to_son = ToSon(include=[
                r'/[0-9]+$'
            ])
            chunksize = min(limit, AdHocHandler.CHUNKSIZE)
            while True:
                rows = result.fetchmany(chunksize)
                if len(rows) == 0:
                    break
                for row in rows:
                    if not first:
                        f.write(', ')
                    f.write(json_encode(to_son(row)))
                    first = False
            f.write(']}')

    @run_on_executor
    def export_csv(self, path, query, limit):
        with model.session_scope() as session, open(path, 'w') as f:
            writer = csv.writer(f)
            result = session.execute(query)
            writer.writerow([c.name for c in result.context.cursor.description])

            chunksize = min(limit, AdHocHandler.CHUNKSIZE)
            while True:
                rows = result.fetchmany(chunksize)
                if len(rows) == 0:
                    break
                writer.writerows(rows)

    @gen.coroutine
    def as_json(self, query, limit):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, 'query_result.json')
            yield self.export_json(path, query, limit)

            self.set_header("Content-Type", "application/json")
            self.set_header(
                'Content-Disposition', 'attachment; filename=query_result.json')
            self.transfer_file(path)
        self.finish()

    @gen.coroutine
    def as_csv(self, query, limit):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, 'query_result.csv')
            yield self.export_csv(path, query, limit)

            self.set_header("Content-Type", "text/csv")
            self.set_header(
                'Content-Disposition', 'attachment; filename=query_result.csv')
            self.transfer_file(path)
        self.finish()

    def transfer_file(self, path):
        with open(path, 'rb') as f:
            while True:
                data = f.read(AdHocHandler.BUF_SIZE)
                if not data:
                    break
                self.write(data)


class SqlFormatHandler(handlers.BaseHandler):
    @handlers.authz('consultant')
    def post(self):
        query = to_basestring(self.request.body)
        query = sqlparse.format(
            query, keyword_case='upper', identifier_case='lower',
            reindent=True, indent_width=4)

        self.set_header("Content-Type", "text/plain")
        self.write(utf8(query))
        self.finish()
