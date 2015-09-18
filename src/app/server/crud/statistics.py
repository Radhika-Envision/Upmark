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

import crud.survey
import handlers
import model
import logging

from utils import reorder, ToSon, truthy, updater
import numpy


log = logging.getLogger('app.crud.statistics')

class FunctionHandler(handlers.Paginate, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, survey_id):
        parent_id = self.get_argument("parentId", None)
        with model.session_scope() as session:
            try:
                responseNodes = session.query(model.ResponseNode)\
                    .join(model.ResponseNode.qnode)\
                    .options(joinedload(model.ResponseNode.qnode))\
                    .filter(model.ResponseNode.survey_id==survey_id)\
                    .filter(model.QuestionNode.parent_id==parent_id)

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
                     if res["qid"] == str(responseNode.qnode.id)]
                if len(r) == 0:
                    r = { "qid": str(responseNode.qnode.id),
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
                # r["total"] = sum(data)
                # r["mean"] = r["total"] / r["count"]
                numpy_array = numpy.array(data)
                r["std"] = numpy.std(numpy_array)
                r["quartile"] = [numpy.percentile(numpy_array, 25), 
                                numpy.percentile(numpy_array, 50),
                                numpy.percentile(numpy_array, 75)]
                # r.pop("data", None)

        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(response))
        self.finish()
