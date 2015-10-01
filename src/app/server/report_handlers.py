import uuid
import json

import sqlalchemy
from sqlalchemy.orm import aliased
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

            qnode_query = (session.query(QA, QB)
                .outerjoin(QB, QA.id == QB.id)

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

            MA = model.Measure
            MB = aliased(model.Measure, name='measure_b')
            QMA = model.QnodeMeasure
            QMB = aliased(model.QnodeMeasure, name='qnode_measure_b')

            qnode_measure_query = (session.query(QMA, QMB)
                .outerjoin(QMB,
                           (QMA.measure_id == QMB.measure_id) &
                           (QMA.qnode_id == QMB.qnode_id))

                # Basic survey membership
                .filter(QMA.survey_id == survey_id_a,
                        QMB.survey_id == survey_id_b)

                .outerjoin(QA, (QMA.survey_id == QA.survey_id) & (QMA.qnode_id == QA.id))
                .outerjoin(QB, (QMB.survey_id == QB.survey_id) & (QMB.qnode_id == QB.id))
                .outerjoin(MA, (QMA.survey_id == MA.survey_id) & (QMA.measure_id == MA.id))
                .outerjoin(MB, (QMB.survey_id == MB.survey_id) & (QMB.measure_id == MB.id))

                # Filter for modified objects
                #.filter((QA.title != QB.title) |
                        #(QA.description != QB.description) |
                        #(QA.parent_id != QB.parent_id))

                # Filter for modified objects
                .filter((MA.id == None) | (MB.id == None))
                #.filter((MA.title != MB.title) |
                        #(MA.intent != MB.intent) |
                        #(MA.inputs != MB.inputs) |
                        #(MA.scenario != MB.scenario) |
                        #(MA.questions != MB.questions) |
                        #(MA.response_type != MB.response_type) |
                        #(MA.weight != MB.weight) |
                        #(QMA.qnode_id != QMB.qnode_id))
            )

            qnode_query = self.paginate(qnode_query)
            qnode_measure_query = self.paginate(qnode_measure_query)
            import pprint
            rs = pprint.pformat(qnode_query.all() + qnode_measure_query.all())

        #self.set_header("Content-Type", "application/json")
        self.set_header("Content-Type", "text/plain")
        self.write(tornado.escape.utf8(rs))
        self.finish()
