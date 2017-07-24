import json

import numpy
from sqlalchemy.orm import joinedload
import tornado.web

import base_handler
from crud.approval import APPROVAL_STATES
import errors
import model
import logging


log = logging.getLogger('app.report.sub_stats')


class StatisticsHandler(base_handler.Paginate, base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self, program_id, survey_id):
        parent_id = self.get_argument("parentId", None)
        approval = self.get_argument("approval", "draft")
        approval_index = APPROVAL_STATES.index(approval)
        included_approval_states = APPROVAL_STATES[approval_index:]

        with model.session_scope() as session:
            user_session = self.get_user_session(session)
            survey = session.query(model.Survey).get((survey_id, program_id))
            if not survey:
                raise errors.MissingDocError("No such survey")

            policy = user_session.policy.derive({
                'survey': survey,
                'index': APPROVAL_STATES.index,
                'approval': approval,
            })
            policy.verify('report_chart')

            responseNodes = (
                session.query(model.ResponseNode)
                .join(model.ResponseNode.qnode)
                .join(model.ResponseNode.submission)
                .options(joinedload('qnode'))
                .filter(
                    model.ResponseNode.program_id == program_id,
                    model.QuestionNode.survey_id == survey_id,
                    model.QuestionNode.parent_id == parent_id,
                    model.Submission.approval.in_(included_approval_states),
                    model.Submission.deleted == False,
                    model.QuestionNode.deleted == False))

            response = []
            for responseNode in responseNodes:
                r = [res for res in response
                     if res["qnodeId"] == str(responseNode.qnode.id)]
                if len(r) == 0:
                    r = {
                        "qnodeId": str(responseNode.qnode.id),
                        "title": str(responseNode.qnode.title),
                        "data": [],
                    }
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
                r["quartile"] = [
                    numpy.percentile(numpy_array, 25),
                    numpy.percentile(numpy_array, 50),
                    numpy.percentile(numpy_array, 75),
                ]

        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(response))
        self.finish()
