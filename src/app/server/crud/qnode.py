import datetime
import logging
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.orm import aliased, joinedload
from sqlalchemy.sql.expression import literal

from activity import Activities
import crud
import handlers
import model
from utils import reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.qnode')


class QuestionNodeHandler(
        handlers.Paginate, crud.survey.SurveyCentric, handlers.BaseHandler):

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

            self.check_browse_survey(session, self.survey_id,
                                     qnode.hierarchy_id)

            to_son = ToSon(
                # Fields to match from any visited object
                r'/id$',
                r'/title$',
                r'/seq$',
                r'/deleted$',
                r'/total_weight$',
                r'/n_measures$',
                r'/is_editable$',
                r'/survey/tracking_id$',
                r'/survey/created$',
                # Fields to match from only the root object
                r'<^/description$',
                # Ascend into nested parent objects
                r'/parent$',
                r'/hierarchy$',
                r'/hierarchy/structure.*$',
                r'/hierarchy/survey$',
                # Response types needed here when creating a new measure
                r'/response_types.*$',
            )
            if self.current_user.role == 'clerk':
                to_son.exclude(r'/total_weight$')
            son = to_son(qnode)

            sibling_query = (session.query(model.QuestionNode)
                .filter(model.QuestionNode.survey_id == qnode.survey_id,
                        model.QuestionNode.hierarchy_id == qnode.hierarchy_id,
                        model.QuestionNode.parent_id == qnode.parent_id,
                        model.QuestionNode.deleted == False))

            prev = (sibling_query
                .filter(model.QuestionNode.seq < qnode.seq)
                .order_by(model.QuestionNode.seq.desc())
                .first())
            next_ = (sibling_query
                .filter(model.QuestionNode.seq > qnode.seq)
                .order_by(model.QuestionNode.seq)
                .first())

            if prev is not None:
                son['prev'] = str(prev.id)
            if next_ is not None:
                son['next'] = str(next_.id)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        '''Get list.'''
        level = self.get_argument('level', '')
        if level != '':
            self.query_by_level(level)
            return

        hierarchy_id = self.get_argument('hierarchyId', '')
        parent_id = self.get_argument('parentId', '')
        root = self.get_argument('root', None)
        term = self.get_argument('term', '')
        parent_not = self.get_argument('parent__not', '')
        deleted = self.get_argument('deleted', '')

        if root is not None and parent_id != '':
            raise handlers.ModelError(
                "Can't specify parent ID when requesting roots")
        if hierarchy_id == '' and parent_id == '':
            raise handlers.ModelError(
                "Hierarchy or parent ID required")

        with model.session_scope() as session:
            query = (session.query(model.QuestionNode)
                .filter(model.QuestionNode.survey_id == self.survey_id))

            if hierarchy_id != '':
                self.check_browse_survey(session, self.survey_id, hierarchy_id)
                query = query.filter_by(hierarchy_id=hierarchy_id)
            if parent_id != '':
                query = query.filter_by(parent_id=parent_id)
            if root is not None:
                query = query.filter_by(parent_id=None)
            if term is not None:
                query = query.filter(
                    model.QuestionNode.title.ilike('%{}%'.format(term)))
            if parent_not != '':
                query = query.filter(model.QuestionNode.parent_id != parent_not)

            if deleted != '':
                deleted = truthy(deleted)
                query = query.filter(model.QuestionNode.deleted == deleted)

            query = query.order_by(model.QuestionNode.seq,
                                   model.QuestionNode.deleted.desc())

            query = self.paginate(query, optional=True)

            to_son = ToSon(
                # Fields to match from any visited object
                r'/id$',
                r'/title$',
                r'/seq$',
                r'/deleted$',
                r'/n_measures$',
                r'/total_weight$',
                # Descend into nested objects
                r'/[0-9]+$',
            )
            if truthy(self.get_argument('desc', False)):
                to_son.add(r'</description$')
            if self.current_user.role == 'clerk':
                to_son.exclude(r'/total_weight$')

            qnodes = list(query.all())
            hierarchy_ids = {q.hierarchy_id for q in qnodes}
            for hid in hierarchy_ids:
                self.check_browse_survey(session, self.survey_id, hid)

            sons = to_son(qnodes)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    def query_by_level(self, level):
        level = int(level)
        hierarchy_id = self.get_argument('hierarchyId', '')
        term = self.get_argument('term', '')
        parent_not = self.get_argument('parent__not', None)
        deleted = self.get_argument('deleted', '')
        if deleted != '':
            deleted = truthy(deleted)
        else:
            deleted = None

        if hierarchy_id == '':
            raise handlers.ModelError("Hierarchy ID required")

        with model.session_scope() as session:
            # Use Postgres' WITH statement
            # http://www.postgresql.org/docs/9.1/static/queries-with.html
            # http://docs.sqlalchemy.org/en/rel_1_0/orm/query.html#sqlalchemy.orm.query.Query.cte
            # http://stackoverflow.com/a/28084743/320036

            # Start by selecting root nodes
            QN1 = model.QuestionNode
            start = (session.query(QN1,
                                   literal(0).label('level'),
                                   array([QN1.seq]).label('path'),
                                   (QN1.seq + 1).concat('.').label('pathstr'),
                                   (QN1.deleted).label('any_deleted'))
                .filter(QN1.parent_id == None,
                        QN1.survey_id == self.survey_id,
                        QN1.hierarchy_id == hierarchy_id)
                .cte(name='root', recursive=True))

            # Now iterate down the tree to the desired level
            QN2 = aliased(model.QuestionNode, name='qnode2')
            recurse = (session.query(QN2,
                                     (start.c.level + 1).label('level'),
                                     start.c.path.concat(QN2.seq).label('path'),
                                     start.c.pathstr.concat(QN2.seq + 1)
                                        .concat('.').label('pathstr'),
                                     (start.c.any_deleted | QN2.deleted)
                                        .label('any_deleted'))
                .filter(QN2.parent_id == start.c.id,
                        QN2.survey_id == start.c.survey_id,
                        QN2.hierarchy_id == start.c.hierarchy_id,
                        start.c.level <= level))

            # Combine iterated result with root
            cte = start.union_all(recurse)

            # Discard all but the lowest level
            subquery = (session.query(cte.c.id, cte.c.pathstr, cte.c.any_deleted)
                .filter(cte.c.level == level)
                .order_by(cte.c.path)
                .subquery())

            # Select again to get the actual qnodes
            query = (session.query(
                    model.QuestionNode, subquery.c.pathstr, subquery.c.any_deleted)
                .filter(model.QuestionNode.survey_id == self.survey_id)
                .join(subquery,
                      model.QuestionNode.id == subquery.c.id))

            if parent_not == '':
                query = query.filter(model.QuestionNode.parent_id != None)
            elif parent_not is not None:
                query = query.filter(model.QuestionNode.parent_id != parent_not)

            if term != '':
                query = query.filter(
                    model.QuestionNode.title.ilike('%{}%'.format(term)))

            if deleted is not None:
                query = query.filter(subquery.c.any_deleted == deleted)

            query = self.paginate(query)

            to_son = ToSon(
                # Fields to match from any visited object
                r'/id$',
                r'/title$',
                r'/deleted$',
                r'/n_measures$'
            )
            if truthy(self.get_argument('desc', False)):
                to_son.add(r'</description$')
            if self.current_user.role == 'clerk':
                to_son.exclude(r'/total_weight$')

            sons = []
            for qnode, path, deleted in query.all():
                son = to_son(qnode)
                son['path'] = path
                son['anyDeleted'] = deleted
                sons.append(son)

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

                # Need to flush so object has an ID to record action against.
                session.flush()

                qnode.update_stats_ancestors()
                qnode_id = str(qnode.id)

                act = Activities(session)
                act.record(self.current_user, qnode, ['create'])
                if not act.has_subscription(self.current_user, qnode):
                    act.subscribe(self.current_user, qnode.survey)
                    self.reason("Subscribed to program")

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

                survey = qnode.survey
                hierarchy = qnode.hierarchy
                parent = qnode.parent

                act = Activities(session)
                if not qnode.deleted:
                    act.record(self.current_user, qnode, ['delete'])
                if not act.has_subscription(self.current_user, qnode):
                    act.subscribe(self.current_user, survey)
                    self.reason("Subscribed to program")

                qnode.deleted = True

                if hierarchy is not None:
                    hierarchy.qnodes.reorder()
                if parent is not None:
                    parent.children.reorder()
                    parent.update_stats_ancestors()

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

        parent_id = self.get_argument('parentId', '')

        try:
            with model.session_scope() as session:
                qnode = session.query(model.QuestionNode)\
                    .get((qnode_id, self.survey_id))
                if qnode is None:
                    raise ValueError("No such object")
                self._update(session, qnode, self.request_son)

                verbs = []
                if session.is_modified(qnode):
                    verbs.append('update')

                nodes_requiring_update = set()
                if parent_id != '' and str(qnode.parent_id) != parent_id:
                    # Change parent
                    old_parent = qnode.parent
                    new_parent = session.query(model.QuestionNode)\
                        .get((parent_id, self.survey_id))
                    if new_parent is None:
                        raise handlers.ModelError("No such question node")
                    old_parent.children.remove(qnode)
                    old_parent.children.reorder()
                    new_parent.children.append(qnode)
                    new_parent.children.reorder()
                    nodes_requiring_update.add(old_parent)
                    nodes_requiring_update.add(qnode)
                    self.reason("Moved from %s to %s" % (
                        old_parent.title, new_parent.title))
                    verbs.append('relation')

                if qnode.deleted:
                    # Get a reference to the collection before changing the
                    # deleted flag - otherwise, if a query is needed to
                    # instantiate the collection, it will seem as if the object
                    # is already in the collection and insert will not work as
                    # expected.
                    if qnode.parent:
                        collection = qnode.parent.children
                    else:
                        collection = qnode.hierarchy.qnodes
                    qnode.deleted = False
                    collection.insert(qnode.seq, qnode)
                    collection.reorder()
                    nodes_requiring_update.add(qnode)
                    verbs.append('undelete')

                for n in nodes_requiring_update:
                    n.update_stats_ancestors()

                act = Activities(session)
                act.record(self.current_user, qnode, verbs)

                if not act.has_subscription(self.current_user, qnode):
                    act.subscribe(self.current_user, qnode.survey)
                    self.reason("Subscribed to program")

        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such question node")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(qnode_id)

    def _update(self, session, qnode, son):
        '''Apply user-provided data to the saved model.'''
        update = updater(qnode)
        update('title', son)
        update('description', son, sanitise=True)

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

                act = Activities(session)
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
                    act.record(self.current_user, parent, ['reorder_children'])
                    if not act.has_subscription(self.current_user, parent):
                        act.subscribe(self.current_user, parent.survey)
                        self.reason("Subscribed to program")
                elif root is not None:
                    hierarchy = session.query(model.Hierarchy)\
                        .get((hierarchy_id, self.survey_id))
                    if hierarchy is None:
                        raise handlers.MissingDocError("No such hierarchy")
                    log.debug("Reordering children of: %s", hierarchy)
                    reorder(hierarchy.qnodes, son)
                    act.record(
                        self.current_user, hierarchy, ['reorder_children'])
                    if not act.has_subscription(self.current_user, hierarchy):
                        act.subscribe(self.current_user, hierarchy.survey)
                        self.reason("Subscribed to program")
                else:
                    raise handlers.ModelError(
                        "Hierarchy or parent ID required")

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)

        self.query()
