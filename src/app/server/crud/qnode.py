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

from utils import reorder, ToSon, updater


log = logging.getLogger('app.crud.qnode')


class QuestionNodeHandler(crud.survey.SurveyCentric, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, qnode_id):
        if qnode_id == '':
            self.query()
            return

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

            to_son = ToSon(include=[
                # Fields to match from any visited object
                r'/id$',
                r'/title$',
                r'/seq$',
                r'/is_open$',
                r'/is_editable$',
                # Fields to match from only the root object
                r'^/description$',
                # Ascend into nested parent objects
                r'/parent$',
                r'/hierarchy$',
                r'/hierarchy/structure.*$',
                r'/hierarchy/survey$'
            ])
            son = to_son(qnode)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        '''Get list.'''
        hierarchy_id = self.get_argument('hierarchyId', '')
        parent_id = self.get_argument('parentId', '')
        root = self.get_argument('root', None)

        if root is not None and parent_id != '':
            raise handlers.ModelError(
                "Can't specify parent ID when requesting roots")
        if hierarchy_id == '' and parent_id == '':
            raise handlers.ModelError(
                "Hierarchy or parent ID required")

        with model.session_scope() as session:
            query = session.query(model.QuestionNode)\
                .filter_by(survey_id=self.survey_id)

            if hierarchy_id != '':
                query = query.filter_by(hierarchy_id=hierarchy_id)
            if parent_id != '':
                query = query.filter_by(parent_id=parent_id)
            if root is not None:
                query = query.filter_by(parent_id=None)

            query = query.order_by(model.QuestionNode.seq)

            to_son = ToSon(include=[
                # Fields to match from any visited object
                r'/id$',
                r'/title$',
                r'/seq$',
                # Descend into nested objects
                r'/[0-9]+$',
            ])
            sons = to_son(query.all())

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

        self.check_editable()

        try:
            with model.session_scope() as session:
                qnode = model.QuestionNode(survey_id=self.survey_id)
                self._update(session, qnode, self.request_son)
                log.debug("new: %s", qnode)

                if hierarchy_id != '':
                    hierarchy = session.query(model.Hierarchy)\
                        .get((hierarchy_id, self.survey_id))
                    if hierarchy is None:
                        raise handlers.ModelError("No such hierarchy")
                else:
                    hierarchy = None
                log.debug("hierarchy: %s", hierarchy)

                if parent_id != '':
                    parent = session.query(model.QuestionNode)\
                        .get((parent_id, self.survey_id))
                    if parent is None:
                        raise handlers.ModelError("Parent does not exist")
                    if hierarchy is None:
                        hierarchy = parent.hierarchy
                    elif parent.hierarchy != hierarchy:
                        raise handlers.ModelError(
                            "Parent does not belong to that hierarchy")
                else:
                    parent = None

                qnode.hierarchy = hierarchy

                if parent is not None:
                    log.debug("Appending to parent")
                    parent.children.append(qnode)
                    parent.children.reorder()
                    log.debug("committing: %s", parent.children)
                elif hierarchy is not None:
                    log.debug("Appending to hierarchy")
                    hierarchy.qnodes.append(qnode)
                    hierarchy.qnodes.reorder()
                    log.debug("committing: %s", hierarchy.qnodes)
                else:
                    raise handlers.ModelError("Parent or hierarchy ID required")

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

        self.check_editable()

        try:
            with model.session_scope() as session:
                qnode = session.query(model.QuestionNode)\
                    .get((qnode_id, self.survey_id))
                if qnode is None:
                    raise ValueError("No such object")
                log.debug("deleting: %s", qnode)

                if len(qnode.qnode_measures) > 0:
                    raise handlers.ModelError("Question node is in use")

                hierarchy = None
                parent = None
                if qnode.hierarchy is not None:
                    hierarchy = qnode.hierarchy
                if qnode.parent is not None:
                    parent = qnode.parent
                session.delete(qnode)
                if hierarchy is not None:
                    hierarchy.qnodes.reorder()
                if parent is not None:
                    parent.children.reorder()
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

        try:
            with model.session_scope() as session:
                qnode = session.query(model.QuestionNode)\
                    .get((qnode_id, self.survey_id))
                if qnode is None:
                    raise ValueError("No such object")
                log.debug("updating: %s", qnode)

                self._update(session, qnode, self.request_son)

        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such question node")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(qnode_id)

    def _update(self, session, qnode, son):
        '''Apply user-provided data to the saved model.'''
        update = updater(qnode)
        update('title', son)
        update('description', son)

    def ordering(self):
        '''Change the order of all children in a parent's collection.'''

        hierarchy_id = self.get_argument('hierarchyId', '')
        parent_id = self.get_argument('parentId', '')
        root = self.get_argument('root', None)

        if root is None and parent_id == '':
            raise handlers.ModelError(
                "Parent ID required, or specify 'root=' for root nodes")
        if root is not None and parent_id != '':
            raise handlers.ModelError(
                "Can't specify both 'root=' and parent ID")
            if hierarchy_id == '':
                raise handlers.ModelError(
                    "Hierarchy ID is required for operating on root nodes")

        son = json_decode(self.request.body)
        try:
            with model.session_scope() as session:
                if parent_id != '':
                    parent = session.query(model.QuestionNode)\
                        .get((parent_id, self.survey_id))
                    if parent is None:
                        raise handlers.MissingDocError(
                            "Parent question node does not exist")
                    if hierarchy_id != '':
                        if hierarchy_id != str(parent.hierarchy_id):
                            raise handlers.MissingDocError(
                                "Parent does not belong to that hierarchy")
                    log.debug("Reordering children of: %s", parent)
                    reorder(parent.children, son)
                elif root is not None:
                    hierarchy = session.query(model.Hierarchy)\
                        .get((hierarchy_id, self.survey_id))
                    if hierarchy is None:
                        raise handlers.MissingDocError("No such hierarchy")
                    log.debug("Reordering children of: %s", hierarchy)
                    reorder(hierarchy.qnodes, son)
                else:
                    raise handlers.ModelError(
                        "Hierarchy or parent ID required")

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)

        self.query()
