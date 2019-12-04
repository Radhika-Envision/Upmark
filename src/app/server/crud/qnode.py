import logging

from tornado.escape import json_decode, json_encode
import tornado.web
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.orm import aliased, joinedload
from sqlalchemy.sql.expression import literal

from activity import Activities
import base_handler
import errors
import model
from score import Calculator
from utils import reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.qnode')


class QuestionNodeHandler(base_handler.Paginate, base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self, qnode_id):
        if not qnode_id:
            self.query()
            return

        program_id = self.get_argument('programId', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)
            qnode = (
                session.query(model.QuestionNode)
                .options(joinedload('program'))
                .options(joinedload('program.surveygroups'))
                .get((qnode_id, program_id)))
            if not qnode:
                raise errors.MissingDocError("No such category")

            policy = user_session.policy.derive({
                'survey': qnode.survey,
                'surveygroups': qnode.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('qnode_view')

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
                r'^/error$',
                r'^/group$',
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
            if user_session.user.role == 'clerk':
                to_son.exclude(r'/total_weight$')
            son = to_son(qnode)

            sibling_query = (
                session.query(model.QuestionNode)
                .filter(model.QuestionNode.program_id == qnode.program_id,
                        model.QuestionNode.survey_id == qnode.survey_id,
                        model.QuestionNode.parent_id == qnode.parent_id,
                        model.QuestionNode.deleted == False))

            prev = (
                sibling_query
                .filter(model.QuestionNode.seq < qnode.seq)
                .order_by(model.QuestionNode.seq.desc())
                .first())
            next_ = (
                sibling_query
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
        if level:
            self.query_by_level(level)
            return

        program_id = self.get_argument('programId', '')
        survey_id = self.get_argument('surveyId', '')
        parent_id = self.get_argument('parentId', '')
        root = self.get_argument('root', None)
        term = self.get_argument('term', '')
        parent_not = self.get_argument('parent__not', '')
        deleted = self.get_argument('deleted', '')

        if root is not None and parent_id:
            raise errors.ModelError(
                "Can't specify parent ID when requesting roots")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            if parent_id:
                parent = (
                    session.query(model.QuestionNode)
                    .options(joinedload('survey'))
                    .options(joinedload('program'))
                    .options(joinedload('program.surveygroups'))
                    .get((parent_id, program_id)))
                if not parent:
                    raise errors.MissingDocError("No such parent category")
                if survey_id and survey_id != str(parent.survey_id):
                    raise errors.ModelError("Category is not in that survey")
                survey = parent.survey
            elif survey_id:
                survey = (
                    session.query(model.Survey)
                    .options(joinedload('program'))
                    .options(joinedload('program.surveygroups'))
                    .get((survey_id, program_id)))
                if not survey:
                    raise errors.MissingDocError("No such survey")
            else:
                raise errors.ModelError("Survey or parent ID required")

            policy = user_session.policy.derive({
                'program': survey.program,
                'survey': survey,
                'surveygroups': survey.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('qnode_view')

            query = (
                session.query(model.QuestionNode)
                .filter(model.QuestionNode.program_id == program_id))

            if survey_id:
                query = query.filter_by(survey_id=survey_id)

            if parent_id:
                query = query.filter_by(parent_id=parent_id)
            elif root is not None:
                query = query.filter_by(parent_id=None)

            if term:
                query = query.filter(
                    model.QuestionNode.title.ilike('%{}%'.format(term)))
            if parent_not:
                query = query.filter(
                    model.QuestionNode.parent_id != parent_not)

            if deleted:
                deleted = truthy(deleted)
                query = query.filter(model.QuestionNode.deleted == deleted)

            query = query.order_by(model.QuestionNode.seq,
                                   model.QuestionNode.deleted.desc())

            query = self.paginate(query, optional=True)

            to_son = ToSon(
                # Fields to match from any visited object
                r'/ob_type$',
                r'/id$',
                r'/title$',
                r'/group$',
                r'/seq$',
                r'/deleted$',
                r'/n_measures$',
                r'/total_weight$',
                r'^/[0-9]+/error$',
                r'/parent$',
                r'/survey$',
                r'/survey/structure.*$',
                r'/survey/program$',
                # Descend into nested objects
                r'/[0-9]+$',
            )
            if truthy(self.get_argument('desc', False)):
                to_son.add(r'</description$')
            if user_session.user.role == 'clerk':
                to_son.exclude(r'/total_weight$')

            sons = to_son(query.all())

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    def query_by_level(self, level):
        level = int(level)
        program_id = self.get_argument('programId', '')
        survey_id = self.get_argument('surveyId', '')
        term = self.get_argument('term', '')
        parent_not = self.get_argument('parent__not', None)
        deleted = self.get_argument('deleted', '')
        if deleted != '':
            deleted = truthy(deleted)
        else:
            deleted = None

        if not survey_id:
            raise errors.ModelError("Survey ID required")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            survey = (
                session.query(model.Survey)
                .options(joinedload('program'))
                .options(joinedload('program.surveygroups'))
                .get((survey_id, program_id)))
            policy = user_session.policy.derive({
                'program': survey.program,
                'survey': survey,
                'surveygroups': survey.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('qnode_view')

            # Use Postgres' WITH statement
            # http://www.postgresql.org/docs/9.1/static/queries-with.html
            # http://docs.sqlalchemy.org/en/rel_1_0/orm/query.html#sqlalchemy.orm.query.Query.cte
            # http://stackoverflow.com/a/28084743/320036

            # Start by selecting root nodes
            QN1 = model.QuestionNode
            start = (
                session.query(
                    QN1,
                    literal(0).label('level'),
                    array([QN1.seq]).label('path'),
                    (QN1.seq + 1).concat('.').label('pathstr'),
                    (QN1.deleted).label('any_deleted'))
                .filter(QN1.parent_id == None,
                        QN1.program_id == program_id,
                        QN1.survey_id == survey_id)
                .cte(name='root', recursive=True))

            # Now iterate down the tree to the desired level
            QN2 = aliased(model.QuestionNode, name='qnode2')
            recurse = (
                session.query(
                    QN2,
                    (start.c.level + 1).label('level'),
                    start.c.path.concat(QN2.seq).label('path'),
                    start.c.pathstr.concat(QN2.seq + 1).concat('.').label(
                        'pathstr'),
                    (start.c.any_deleted | QN2.deleted).label(
                        'any_deleted'))
                .filter(QN2.parent_id == start.c.id,
                        QN2.program_id == start.c.program_id,
                        QN2.survey_id == start.c.survey_id,
                        start.c.level <= level))

            # Combine iterated result with root
            cte = start.union_all(recurse)

            # Discard all but the lowest level
            subquery = (
                session.query(cte.c.id, cte.c.pathstr, cte.c.any_deleted)
                .filter(cte.c.level == level)
                .order_by(cte.c.path)
                .subquery())

            # Select again to get the actual qnodes
            query = (
                session.query(
                    model.QuestionNode, subquery.c.pathstr,
                    subquery.c.any_deleted)
                .filter(model.QuestionNode.program_id == program_id)
                .join(subquery,
                      model.QuestionNode.id == subquery.c.id))

            if parent_not == '':
                query = query.filter(
                    model.QuestionNode.parent_id != None)
            elif parent_not is not None:
                query = query.filter(
                    model.QuestionNode.parent_id != parent_not)

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
            if user_session.user.role == 'clerk':
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

    @tornado.web.authenticated
    def post(self, qnode_id):
        '''Create new.'''

        if qnode_id:
            raise errors.MethodError("Can't use POST for existing object")

        program_id = self.get_argument('programId', '')
        survey_id = self.get_argument('surveyId', '')
        parent_id = self.get_argument('parentId', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            program = (
                session.query(model.Program)
                .options(joinedload('surveygroups'))
                .get(program_id))
            if not program:
                raise errors.ModelError("No such program")

            qnode = model.QuestionNode(program=program)
            self._update(session, qnode, self.request_son)
            log.debug("new: %s", qnode)

            if survey_id:
                survey = (
                    session.query(model.Survey)
                    .get((survey_id, program_id)))
                if not survey:
                    raise errors.ModelError("No such survey")
            else:
                survey = None
            log.debug("survey: %s", survey)

            if parent_id:
                parent = (
                    session.query(model.QuestionNode)
                    .get((parent_id, program_id)))
                if not parent:
                    raise errors.ModelError("Parent does not exist")
                if not survey:
                    survey = parent.survey
                elif parent.survey != survey:
                    raise errors.ModelError(
                        "Parent does not belong to that survey")
            else:
                parent = None

            qnode.survey = survey

            if parent:
                log.debug("Appending to parent")
                parent.children.append(qnode)
                parent.children.reorder()
                log.debug("committing: %s", parent.children)
            elif survey:
                log.debug("Appending to survey")
                survey.qnodes.append(qnode)
                survey.qnodes.reorder()
                log.debug("committing: %s", survey.qnodes)
            else:
                raise errors.ModelError("Parent or survey ID required")

            # Need to flush so object has an ID to record action against.
            session.flush()

            policy = user_session.policy.derive({
                'program': qnode.program,
                'survey': qnode.survey,
                'surveygroups': qnode.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('qnode_add')

            calculator = Calculator.structural()
            calculator.mark_qnode_dirty(qnode)
            calculator.execute()

            qnode_id = str(qnode.id)

            act = Activities(session)
            act.record(user_session.user, qnode, ['create'])
            act.ensure_subscription(
                user_session.user, qnode, qnode.program, self.reason)

        self.get(qnode_id)

    @tornado.web.authenticated
    def delete(self, qnode_id):
        '''Delete existing.'''

        if not qnode_id:
            raise errors.MethodError("Question node ID required")

        program_id = self.get_argument('programId', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            qnode = (
                session.query(model.QuestionNode)
                .options(joinedload('program'))
                .options(joinedload('program.surveygroups'))
                .get((qnode_id, program_id)))
            if not qnode:
                raise errors.MissingDocError("No such question node")
            log.debug("deleting: %s", qnode)

            program = qnode.program
            survey = qnode.survey
            parent = qnode.parent

            policy = user_session.policy.derive({
                'program': program,
                'survey': survey,
                'surveygroups': program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('qnode_del')

            act = Activities(session)
            if not qnode.deleted:
                act.record(user_session.user, qnode, ['delete'])
            act.ensure_subscription(
                user_session.user, qnode, qnode.program, self.reason)

            qnode.deleted = True

            calculator = Calculator.structural()
            if parent:
                parent.children.reorder()
                calculator.mark_qnode_dirty(parent)
            else:
                survey.qnodes.reorder()
                calculator.mark_survey_dirty(survey)
            calculator.execute()

        self.finish()

    @tornado.web.authenticated
    def put(self, qnode_id):
        '''Update existing.'''

        if not qnode_id:
            self.ordering()
            return

        program_id = self.get_argument('programId', '')
        parent_id = self.get_argument('parentId', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            qnode = (
                session.query(model.QuestionNode)
                .options(joinedload('program'))
                .options(joinedload('program.surveygroups'))
                .get((qnode_id, program_id)))
            if not qnode:
                raise errors.MissingDocError("No such question node")

            policy = user_session.policy.derive({
                'program': qnode.program,
                'survey': qnode.survey,
                'surveygroups': qnode.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('qnode_edit')

            self._update(session, qnode, self.request_son)

            verbs = []
            if session.is_modified(qnode):
                verbs.append('update')

            calculator = Calculator.structural()
            if parent_id and str(qnode.parent_id) != parent_id:
                # Change parent
                old_parent = qnode.parent
                new_parent = (
                    session.query(model.QuestionNode)
                    .get((parent_id, program_id)))
                if new_parent.survey != qnode.survey:
                    raise errors.ModelError("Can't move to different survey")
                if not new_parent:
                    raise errors.ModelError("No such question node")
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
            act.record(user_session.user, qnode, verbs)
            act.ensure_subscription(
                user_session.user, qnode, qnode.program, self.reason)

        self.get(qnode_id)

    def _update(self, session, qnode, son):
        '''Apply user-provided data to the saved model.'''
        update = updater(qnode, error_factory=errors.ModelError)
        update('title', son)
        update('group', son)
        update('description', son, sanitise=True)


    def ordering(self):
        '''Change the order of all children in a parent's collection.'''

        program_id = self.get_argument('programId', '')
        survey_id = self.get_argument('surveyId', '')
        parent_id = self.get_argument('parentId', '')
        root = self.get_argument('root', None)

        #if parent_id and root is None:
        if parent_id is None and root is None: 
            raise errors.ModelError(
                "Parent ID required, or specify 'root=' for root nodes")
        if root is not None and parent_id:
            raise errors.ModelError(
                "Can't specify both 'root=' and parent ID")
            if not survey_id:
                raise errors.ModelError(
                    "Survey ID is required for operating on root nodes")

        son = json_decode(self.request.body)

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            act = Activities(session)
            if parent_id:
                parent = (
                    session.query(model.QuestionNode)
                    .get((parent_id, program_id)))
                if not parent:
                    raise errors.MissingDocError(
                        "Parent question node does not exist")
                survey = parent.survey
                if survey_id and survey_id != str(survey.id):
                    raise errors.MissingDocError(
                        "Parent does not belong to that survey")
                log.debug("Reordering children of: %s", parent)
                reorder(parent.children, son)
                act.record(user_session.user, parent, ['reorder_children'])
                act.ensure_subscription(
                    user_session.user, parent, parent.program, self.reason)

            elif root is not None:
                survey = (
                    session.query(model.Survey)
                    .get((survey_id, program_id)))
                if not survey:
                    raise errors.MissingDocError("No such survey")
                log.debug("Reordering children of: %s", survey)
                reorder(survey.qnodes, son)
                act.record(
                    user_session.user, survey, ['reorder_children'])
                act.ensure_subscription(
                    user_session.user, survey, survey.program, self.reason)

            else:
                raise errors.ModelError(
                    "Survey or parent ID required")

            policy = user_session.policy.derive({
                'program': survey.program,
                'survey': survey,
                'surveygroups': survey.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('qnode_edit')

        self.query()
