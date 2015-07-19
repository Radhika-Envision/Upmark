import datetime
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.orm import joinedload

import crud.survey
import handlers
import model
import logging

from utils import to_dict, reorder


log = logging.getLogger('app.data_access')


class QuestionNodeHandler(crud.survey.SurveyCentric, handlers.BaseHandler):

    def to_dict(self, qnode, focus)
        # Qnodes that have a measure have no title, so use the measure's own
        # title.
        if qnode.measure is not None:
            son = to_dict(qnode, include={'id', 'seq'})
            son['title'] = qnode.measure.title
            if focus:
                son['measure'] = to_dict(qnode.measure, exclude={'title'})
        else:
            son = to_dict(qnode, include={'id', 'title', 'seq'}
            if focus:
                son['description'] = qnode.description

        # Don't include children: the REST API is cleaner if children are
        # fetched (and reordered) separately.
        return son

    def to_dict_ancestors(self, qnode, focus):
        son = self.to_dict(qnode, focus)

        # All qnodes have either a parent (depth > 1) or a hierarchy
        # (depth = 0).
        if qnode.parent is not None:
            son['parent'] = to_dict_ancestors(qnode.parent, focus=False)
        else:
            son['hierarchy'] = to_dict(qnode.hierarchy, include={'id', 'title'})
            son['hierarchy']['survey'] = to_dict(
                qnode.hierarchy.survey, include={'id', 'title'})

        return son

    @tornado.web.authenticated
    def get(self, qnode_id):
        if qnode_id == '':
            self.query()
            return

        self.check_editable()

        with model.session_scope() as session:
            try:
                qnode = session.query(model.QuestionNode)\
                    .get((qnode_id, self.survey_id))

                if qnode is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such category")

            son = self.to_dict_ancestors(qnode, focus=True)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self):
        '''Get list.'''
        hierarchy_id = self.get_argument('hierarchyId', '')
        parent_id = self.get_argument('parentId', '')
        if hierarchy_id != '' and parent_id != '':
            raise handlers.ModelError(
                "Can't specify both parent and hierarchy IDs")

        sons = []
        with model.session_scope() as session:
            query = session.query(model.QuestionNode)\
                .filter_by(survey_id=self.survey_id)

            if hierarchy_id != '':
                query.filter_by(hierarchy_id=hierarchy_id)
            elif parent_id != '':
                query.filter_by(parent_id=parent_id)
            else:
                raise handlers.ModelError(
                    "Hierarchy or parent ID required")

            query.order_by(model.QuestionNode.seq)

            for ob in query.all():
                sons.append(self.to_dict(ob, focus=False)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('author')
    def post(self, qnode_id):
        '''Create new.'''
        self.check_editable()

        if qnode_id != '':
            raise handlers.MethodError("Can't use POST for existing object")

        hierarchy_id = self.get_argument('hierarchyId', '')
        parent_id = self.get_argument('parentId', '')
        if hierarchy_id != '' and parent_id != '':
            raise handlers.ModelError(
                "Can't specify both parent and hierarchy IDs")

        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                qnode = model.QuestionNode()
                self._update(qnode, son)
                qnode.survey_id = survey_id

                if hierarchy_id != '':
                    hierarchy = session.query(model.Hierarchy)\
                        .get((hierarchy_id, self.survey_id))
                    if hierarchy is None:
                        raise handlers.ModelError("No such hierarchy")
                    hierarchy.children.append(qnode)
                    hierarchy.children.reorder()
                elif parent_id != '':
                    parent = session.query(model.Hierarchy)\
                        .get((hierarchy_id, self.survey_id))
                    if parent is None:
                        raise handlers.ModelError(
                            "Parent category does not exist")
                    parent.children.append(qnode)
                    parent.children.reorder()
                else:
                    raise handlers.ModelError(
                        "Hierarchy or parent ID required")
                session.flush()
                qnode_id = str(qnode.id)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(qnode_id)

    @handlers.authz('author')
    def delete(self, qnode_id):
        '''Delete existing.'''
        self.check_editable()

        if qnode_id == '':
            raise handlers.MethodError("Question node ID required")

        try:
            with model.session_scope() as session:
                qnode = session.query(model.QuestionNode)\
                    .get((qnode_id, self.survey_id))
                if qnode is None:
                    raise ValueError("No such object")

                if qnode.hierarchy is not None:
                    qnode.hierarchy.children.remove(qnode)
                if qnode.parent is not None:
                    qnode.parent.children.remove(qnode)
                session.delete(qnode)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError("Question node is in use")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such question node")

        self.finish()

    @handlers.authz('author')
    def put(self, qnode_id):
        '''Update existing.'''
        self.check_editable()

        if qnode_id == '':
            self.ordering()
            return

        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                qnode = session.query(model.QuestionNode)\
                    .get((qnode_id, self.survey_id))
                if qnode is None:
                    raise ValueError("No such object")
                self._update(qnode, son)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such question node")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(qnode_id)

    def ordering(self):
        '''Change the order of all children in the parent's collection.'''

        hierarchy_id = self.get_argument('hierarchyId', '')
        parent_id = self.get_argument('parentId', '')
        if hierarchy_id != '' and parent_id != '':
            raise handlers.ModelError(
                "Can't specify both parent and hierarchy IDs")

        son = json_decode(self.request.body)
        try:
            with model.session_scope() as session:
                if hierarchy_id != '':
                    hierarchy = session.query(model.Hierarchy)\
                        .get((hierarchy_id, survey_id))
                    if hierarchy is None:
                        raise handlers.MissingDocError("No such hierarchy")
                    reorder(hierarchy.children, son)
                elif parent_id != '':
                    parent = session.query(model.QuestionNode)\
                        .get((parent_id, survey_id))
                    if parent is None:
                        raise handlers.MissingDocError(
                            "Parent question node does not exist")
                    reorder(parent.children, son)
                else:
                    raise handlers.ModelError(
                        "Hierarchy or parent ID required")

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)

        self.query()

    def _update(self, qnode, son):
        '''Apply user-provided data to the saved model.'''
        if son.get('title', '') != '':
            process.title = son['title']
        if son.get('description', '') != '':
            process.description = son['description']
