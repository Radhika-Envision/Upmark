from concurrent.futures import ThreadPoolExecutor
import datetime
import time
import uuid
import json

from tornado import gen
from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.session import make_transient

import handlers
import model
import logging

from utils import reorder, ToSon, truthy, updater
import numpy


log = logging.getLogger('app.statistics_handler')

class StatisticsHandler(handlers.Paginate, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, program_id):
        if self.has_privillege('consultant') or self.has_privillege('authority') :
            pass
        else:
            with model.session_scope() as session:
                purchased_survey = (session.query(model.PurchasedSurvey)
                    .filter_by(program_id=program_id,
                               organisation_id=self.organisation.id)
                    .first())
                log.info("purchased_survey: %s", purchased_survey)
                if purchased_survey==None:
                    raise handlers.AuthzError("You should purchase this survey" +
                        " to see this chart")

        parent_id = self.get_argument("parentId", None)
        approval=self.get_argument("approval", "draft")
        approval_status = ['draft', 'final', 'reviewed', 'approved']
        approval_index = approval_status.index(approval)
        included_approval_status=approval_status[approval_index:4]
        with model.session_scope() as session:
            try:
                responseNodes = (session.query(model.ResponseNode)
                    .join(model.ResponseNode.qnode)
                    .join(model.ResponseNode.assessment)
                    .options(joinedload(model.ResponseNode.qnode))
                    .filter(model.ResponseNode.program_id == program_id,
                            model.QuestionNode.parent_id == parent_id,
                            model.Assessment.approval.in_(included_approval_status),
                            model.Assessment.deleted == False,
                            model.QuestionNode.deleted == False))

                if responseNodes is None:
                    raise ValueError("No such object")
                # if assessment.organisation.id != self.organisation.id:
                #     self.check_privillege('author', 'consultant')
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such survey")


            response = []
            for responseNode in responseNodes:
                r = [res for res in response
                     if res["qnodeId"] == str(responseNode.qnode.id)]
                if len(r) == 0:
                    r = { "qnodeId": str(responseNode.qnode.id),
                        "title": str(responseNode.qnode.title),
                        "data": [] }
                    response.append(r)
                else:
                    r = r[0]

                r["data"].append(responseNode.score)

            for r in response:
                data = r["data"]
                r["min"] = min(data)
                r["max"] = max(data)
                r["count"] = len(data)
                numpy_array = numpy.array(data)
                # r["std"] = numpy.std(numpy_array)
                r["quartile"] = [numpy.percentile(numpy_array, 25),
                                numpy.percentile(numpy_array, 50),
                                numpy.percentile(numpy_array, 75)]

        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(response))
        self.finish()
