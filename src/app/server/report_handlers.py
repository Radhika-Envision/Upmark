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


class DiffHandler(handlers.Paginate, handlers.BaseHandler):

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
            qnode_query = self.construct_qnode_query(
                session, survey_id_a, survey_id_b, hierarchy_id)
            measure_query = self.construct_measure_query(
                session, survey_id_a, survey_id_b, hierarchy_id)

            qnode_query = self.paginate(qnode_query)
            measure_query = self.paginate(measure_query)
            import pprint
            log.error('%s', pprint.pformat(
                qnode_query.all()
                + measure_query.all()
            ))
            to_son = ToSon(include=[
                r'/id$',
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
            son = {}
            son['diff'] = to_son(
                qnode_query.all()
                + measure_query.all()
            )

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def construct_qnode_query(
            self, session, survey_id_a, survey_id_b, hierarchy_id):
        QA = model.QuestionNode
        QB = aliased(model.QuestionNode, name='qnode_b')

        # Find modified / relocated qnodes
        qnode_mod_query = (session.query(QA.id, QB.id)
            .join(QB, QA.id == QB.id)

            # Basic survey membership
            .filter(QA.survey_id == survey_id_a,
                    QB.survey_id == survey_id_b,
                    QA.hierarchy_id == hierarchy_id,
                    QB.hierarchy_id == hierarchy_id)

            # Filter for modified objects
            .filter((QA.title != QB.title) |
                    (QA.description != QB.description) |
                    (QA.parent_id != QB.parent_id) |
                    (QA.seq != QB.seq))
        )

        # Find deleted qnodes
        qnode_del_query = (session.query(QA.id, literal(None))
            .select_from(QA)
            .filter(QA.survey_id == survey_id_a,
                    QA.hierarchy_id == hierarchy_id,
                    ~QA.id.in_(
                        session.query(QB.id)
                            .filter(QB.survey_id == survey_id_b,
                                    QB.hierarchy_id == hierarchy_id)))
        )

        # Find added qnodes
        qnode_add_query = (session.query(literal(None), QB.id)
            .select_from(QB)
            .filter(QB.survey_id == survey_id_b,
                    QB.hierarchy_id == hierarchy_id,
                    ~QB.id.in_(
                        session.query(QA.id)
                            .filter(QA.survey_id == survey_id_a,
                                    QA.hierarchy_id == hierarchy_id)))
        )

        qnode_query = (qnode_mod_query
                       .union_all(qnode_add_query)
                       .union_all(qnode_del_query))
        return qnode_query

    def construct_measure_query(
            self, session, survey_id_a, survey_id_b, hierarchy_id):
        QA = model.QuestionNode
        QB = aliased(model.QuestionNode, name='qnode_b')
        MA = model.Measure
        MB = aliased(model.Measure, name='measure_b')
        QMA = model.QnodeMeasure
        QMB = aliased(model.QnodeMeasure, name='qnode_measure_link_b')

        # Find modified / relocated measures
        measure_mod_query = (session.query(MA.id, MB.id)

            .join(MB, MA.id == MB.id)

            .join(QMA, (QMA.survey_id == MA.survey_id) & (QMA.measure_id == MA.id))
            .join(QMB, (QMB.survey_id == MB.survey_id) & (QMB.measure_id == MB.id))
            .join(QA, (QMA.survey_id == QA.survey_id) & (QMA.qnode_id == QA.id))
            .join(QB, (QMB.survey_id == QB.survey_id) & (QMB.qnode_id == QB.id))

            # Basic survey membership
            .filter(QA.survey_id == survey_id_a,
                    QB.survey_id == survey_id_b,
                    QA.hierarchy_id == hierarchy_id,
                    QB.hierarchy_id == hierarchy_id)

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

        # Find deleted measures
        measure_del_query = (session.query(MA.id, literal(None))
            .select_from(MA)
            .join(QMA, (QMA.survey_id == MA.survey_id) & (QMA.measure_id == MA.id))
            .join(QA, (QMA.survey_id == QA.survey_id) & (QMA.qnode_id == QA.id))
            .filter(QA.survey_id == survey_id_a,
                    QA.hierarchy_id == hierarchy_id,
                    ~QMA.measure_id.in_(
                        session.query(QMB.measure_id)
                            .join(QB, (QMB.survey_id == QB.survey_id) & (QMB.qnode_id == QB.id))
                            .filter(QB.survey_id == survey_id_b,
                                    QB.hierarchy_id == hierarchy_id)))
        )

        # Find added measures
        measure_add_query = (session.query(literal(None), MB.id)
            .select_from(MB)
            .join(QMB, (QMB.survey_id == MB.survey_id) & (QMB.measure_id == MB.id))
            .join(QB, (QMB.survey_id == QB.survey_id) & (QMB.qnode_id == QB.id))
            .filter(QB.survey_id == survey_id_b,
                    QB.hierarchy_id == hierarchy_id,
                    ~QMB.measure_id.in_(
                        session.query(QMA.measure_id)
                            .join(QA, (QMA.survey_id == QA.survey_id) & (QMA.qnode_id == QA.id))
                            .filter(QA.survey_id == survey_id_a,
                                    QA.hierarchy_id == hierarchy_id)))
        )

        measure_query = (measure_mod_query
                         .union_all(measure_add_query)
                         .union_all(measure_del_query))
        return measure_query
