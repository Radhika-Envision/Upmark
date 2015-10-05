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
            QA = model.QuestionNode
            QB = aliased(model.QuestionNode, name='qnode_b')
            MA = model.Measure
            MB = aliased(model.Measure, name='measure_b')
            QMA = model.QnodeMeasure
            QMB = aliased(model.QnodeMeasure, name='qnode_measure_link_b')

            # Find modified / relocated qnodes
            qnode_query = (session.query(QA, QB)
                .join(QB, QA.id == QB.id)

                # Basic survey membership
                .filter(QA.survey_id == survey_id_a,
                        QB.survey_id == survey_id_b,
                        QA.hierarchy_id == hierarchy_id,
                        QB.hierarchy_id == hierarchy_id)

                # Filter for modified objects
                .filter((QA.title != QB.title) |
                        (QA.description != QB.description) |
                        (QA.parent_id != QB.parent_id))
            )

            # Find deleted qnodes
            qnode_del_query = (session.query(QA, literal(None))
                .select_from(QA)
                .filter(QA.survey_id == survey_id_a,
                        QA.hierarchy_id == hierarchy_id,
                        ~QA.id.in_(
                            session.query(QB.id)
                                .filter(QB.survey_id == survey_id_b,
                                        QB.hierarchy_id == hierarchy_id)))
            )

            # Find added qnodes
            qnode_add_query = (session.query(literal(None), QB)
                .select_from(QB)
                .filter(QB.survey_id == survey_id_b,
                        QB.hierarchy_id == hierarchy_id,
                        ~QB.id.in_(
                            session.query(QA.id)
                                .filter(QA.survey_id == survey_id_a,
                                        QA.hierarchy_id == hierarchy_id)))
            )

            # Find modified / relocated measures
            qnode_measure_query = (session.query(QMA, QMB)
                .join(QMB, QMA.measure_id == QMB.measure_id)

                .join(MA, (QMA.survey_id == MA.survey_id) & (QMA.measure_id == MA.id))
                .join(MB, (QMB.survey_id == MB.survey_id) & (QMB.measure_id == MB.id))
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
                        (QMA.qnode_id != QMB.qnode_id))
            )

            # Find deleted measures
            qnode_measure_del_query = (session.query(QMA, literal(None))
                .select_from(QMA)
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
            qnode_measure_add_query = (session.query(literal(None), QMB)
                .select_from(QMB)
                .join(QB, (QMB.survey_id == QB.survey_id) & (QMB.qnode_id == QB.id))
                .filter(QB.survey_id == survey_id_b,
                        QB.hierarchy_id == hierarchy_id,
                        ~QMB.measure_id.in_(
                            session.query(QMA.measure_id)
                                .join(QA, (QMA.survey_id == QA.survey_id) & (QMA.qnode_id == QA.id))
                                .filter(QA.survey_id == survey_id_a,
                                        QA.hierarchy_id == hierarchy_id)))
            )

            #log.error('Query: %s', qnode_query)
            log.error('Query: %s', qnode_del_query)
            #log.error('Query: %s', qnode_measure_query)

            qnode_query = self.paginate(qnode_query)
            qnode_measure_query = self.paginate(qnode_measure_query)
            import pprint
            rs = pprint.pformat(
                qnode_query.all()
                + qnode_del_query.all()
                + qnode_add_query.all()
                + qnode_measure_query.all()
                + qnode_measure_del_query.all()
                + qnode_measure_add_query.all()
            )

        #self.set_header("Content-Type", "application/json")
        self.set_header("Content-Type", "text/plain")
        self.write(tornado.escape.utf8(rs))
        self.finish()
