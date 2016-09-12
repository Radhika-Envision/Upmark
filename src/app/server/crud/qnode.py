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
from score import Calculator
from utils import reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.qnode')


class QuestionNodeHandler(
        handlers.Paginate, crud.program.ProgramCentric, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, qnode_id):
        if qnode_id == '':
            self.query()
            return

        with model.session_scope() as session:
            try:
                qnode = session.query(model.QuestionNode)\
                    .get((qnode_id, self.program_id))

                if qnode is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such category")

            self.check_browse_program(session, self.program_id,
                                     qnode.survey_id)

            to_son = ToSon(
                # Fields to match from any visited object
                r'/ob_type$',
                r'/id$',
                r'/title$',
                r'/seq$',
                r'/deleted$',
                r'/total_weight$',
                r'/n_measures$',
                r'/is_editable$',
                r'/program/tracking_id$',
                r'/program/created$',
                r'/program/hide_aggregate$',
                # Fields to match from only the root object
                r'<^/description$',
                # Ascend into nested parent objects
                r'/parent$',
                r'/survey$',
                r'/survey/structure.*$',
                r'/survey/program$',
                # Response types needed here when creating a new measure
                r'/response_types.*$',
            )
            if self.current_user.role == 'clerk':
                to_son.exclude(r'/total_weight$')
            son = to_son(qnode)

            sibling_query = (session.query(model.QuestionNode)
                .filter(model.QuestionNode.program_id == qnode.program_id,
                        model.QuestionNode.survey_id == qnode.survey_id,
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

        survey_id = self.get_argument('surveyId', '')
        parent_id = self.get_argument('parentId', '')
        root = self.get_argument('root', None)
        term = self.get_argument('term', '')
        parent_not = self.get_argument('parent__not', '')
        deleted = self.get_argument('deleted', '')

        if root is not None and parent_id != '':
            raise handlers.ModelError(
                "Can't specify parent ID when requesting roots")
        if survey_id == '' and parent_id == '':
            raise handlers.ModelError(
                "Survey or parent ID required")

        with model.session_scope() as session:
            query = (session.query(model.QuestionNode)
                .filter(model.QuestionNode.program_id == self.program_id))

            if survey_id != '':
                self.check_browse_program(session, self.program_id, survey_id)
                query = query.filter_by(survey_id=survey_id)
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
            survey_ids = {q.survey_id for q in qnodes}
            for hid in survey_ids:
                self.check_browse_program(session, self.program_id, hid)

            sons = to_son(qnodes)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    def query_by_level(self, level):
        level = int(level)
        survey_id = self.get_argument('surveyId', '')
        term = self.get_argument('term', '')
        parent_not = self.get_argument('parent__not', None)
        deleted = self.get_argument('deleted', '')
        if deleted != '':
            deleted = truthy(deleted)
        else:
            deleted = None

        if survey_id == '':
            raise handlers.ModelError("Survey ID required")

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
                        QN1.program_id == self.program_id,
                        QN1.survey_id == survey_id)
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
                        QN2.program_id == start.c.program_id,
                        QN2.survey_id == start.c.survey_id,
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
                .filter(model.QuestionNode.program_id == self.program_id)
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

        survey_id = self.get_argument('surveyId', '')
        parent_id = self.get_argument('parentId', '')

        self.check_editable()

        try:
            with model.session_scope() as session:
                qnode = model.QuestionNode(program_id=self.program_id)
                self._update(session, qnode, self.request_son)
                log.debug("new: %s", qnode)

                if survey_id != '':
                    survey = session.query(model.Survey)\
                        .get((survey_id, self.program_id))
                    if survey is None:
                        raise handlers.ModelError("No such survey")
                else:
                    survey = None
                log.debug("survey: %s", survey)

                if parent_id != '':
                    parent = session.query(model.QuestionNode)\
                        .get((parent_id, self.program_id))
                    if parent is None:
                        raise handlers.ModelError("Parent does not exist")
                    if survey is None:
                        survey = parent.survey
                    elif parent.survey != survey:
                        raise handlers.ModelError(
                            "Parent does not belong to that survey")
                else:
                    parent = None

                qnode.survey = survey

                if parent is not None:
                    log.debug("Appending to parent")
                    parent.children.append(qnode)
                    parent.children.reorder()
                    log.debug("committing: %s", parent.children)
                elif survey is not None:
                    log.debug("Appending to survey")
                    survey.qnodes.append(qnode)
                    survey.qnodes.reorder()
                    log.debug("committing: %s", survey.qnodes)
                else:
                    raise handlers.ModelError("Parent or survey ID required")

                # Need to flush so object has an ID to record action against.
                session.flush()

                calculator = Calculator.structural()
                calculator.mark_qnode_dirty(qnode)
                calculator.execute()

                qnode_id = str(qnode.id)

                act = Activities(session)
                act.record(self.current_user, qnode, ['create'])
                if not act.has_subscription(self.current_user, qnode):
                    act.subscribe(self.current_user, qnode.program)
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
                    .get((qnode_id, self.program_id))
                if qnode is None:
                    raise ValueError("No such object")
                log.debug("deleting: %s", qnode)

                program = qnode.program
                survey = qnode.survey
                parent = qnode.parent

                act = Activities(session)
                if not qnode.deleted:
                    act.record(self.current_user, qnode, ['delete'])
                if not act.has_subscription(self.current_user, qnode):
                    act.subscribe(self.current_user, program)
                    self.reason("Subscribed to program")

                qnode.deleted = True

                calculator = Calculator.structural()
                if parent is not None:
                    parent.children.reorder()
                    calculator.mark_qnode_dirty(parent)
                else:
                    survey.qnodes.reorder()
                    calculator.mark_survey_dirty(survey)
                calculator.execute()

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
                    .get((qnode_id, self.program_id))
                if qnode is None:
                    raise ValueError("No such object")
                self._update(session, qnode, self.request_son)

                verbs = []
                if session.is_modified(qnode):
                    verbs.append('update')

                calculator = Calculator.structural()
                if parent_id != '' and str(qnode.parent_id) != parent_id:
                    # Change parent
                    old_parent = qnode.parent
                    new_parent = session.query(model.QuestionNode)\
                        .get((parent_id, self.program_id))
                    if new_parent is None:
                        raise handlers.ModelError("No such question node")
                    old_parent.children.remove(qnode)
                    old_parent.children.reorder()
                    new_parent.children.append(qnode)
                    new_parent.children.reorder()
                    calculator.mark_qnode_dirty(old_parent)
                    calculator.mark_qnode_dirty(qnode)
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
                        collection = qnode.survey.qnodes
                    qnode.deleted = False
                    collection.insert(qnode.seq, qnode)
                    collection.reorder()
                    calculator.mark_qnode_dirty(qnode)
                    verbs.append('undelete')

                calculator.execute()

                act = Activities(session)
                act.record(self.current_user, qnode, verbs)

                if not act.has_subscription(self.current_user, qnode):
                    act.subscribe(self.current_user, qnode.program)
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

        survey_id = self.get_argument('surveyId', '')
        parent_id = self.get_argument('parentId', '')
        root = self.get_argument('root', None)

        if root is None and parent_id == '':
            raise handlers.ModelError(
                "Parent ID required, or specify 'root=' for root nodes")
        if root is not None and parent_id != '':
            raise handlers.ModelError(
                "Can't specify both 'root=' and parent ID")
            if survey_id == '':
                raise handlers.ModelError(
                    "Survey ID is required for operating on root nodes")

        son = json_decode(self.request.body)
        try:
            with model.session_scope() as session:

                act = Activities(session)
                if parent_id != '':
                    parent = session.query(model.QuestionNode)\
                        .get((parent_id, self.program_id))
                    if parent is None:
                        raise handlers.MissingDocError(
                            "Parent question node does not exist")
                    if survey_id != '':
                        if survey_id != str(parent.survey_id):
                            raise handlers.MissingDocError(
                                "Parent does not belong to that survey")
                    log.debug("Reordering children of: %s", parent)
                    reorder(parent.children, son)
                    act.record(self.current_user, parent, ['reorder_children'])
                    if not act.has_subscription(self.current_user, parent):
                        act.subscribe(self.current_user, parent.program)
                        self.reason("Subscribed to program")
                elif root is not None:
                    survey = session.query(model.Survey)\
                        .get((survey_id, self.program_id))
                    if survey is None:
                        raise handlers.MissingDocError("No such survey")
                    log.debug("Reordering children of: %s", survey)
                    reorder(survey.qnodes, son)
                    act.record(
                        self.current_user, survey, ['reorder_children'])
                    if not act.has_subscription(self.current_user, survey):
                        act.subscribe(self.current_user, survey.program)
                        self.reason("Subscribed to program")
                else:
                    raise handlers.ModelError(
                        "Survey or parent ID required")

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)

        self.query()
