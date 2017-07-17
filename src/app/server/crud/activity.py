from concurrent.futures import ThreadPoolExecutor
import datetime
import logging
import time

from tornado import gen
from tornado.concurrent import run_on_executor
from tornado.escape import json_encode
import tornado.web

from activity import Activities
import base_handler
import errors
import model
from utils import ToSon, updater


MAX_WORKERS = 4

log = logging.getLogger('app.crud.activity')


perf_time = time.perf_counter()
perf_start = None


def perf():
    global perf_start, perf_time
    if perf_start is None:
        perf_start = time.perf_counter()
        perf_time = 0.0
    else:
        now = time.perf_counter()
        perf_time += now - perf_start
        perf_start = now
    return perf_time


class ActivityHandler(base_handler.BaseHandler):

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    TO_SON = ToSon(
        r'/id$',
        r'/created$',
        r'/message$',
        r'/sticky$',
        r'/subject$',
        r'/subject/name$',
        r'/verbs/?.*$',
        r'/organisation$',
        r'/ob_type$',
        r'/ob_ids$',
        r'/object_ids/?.*$',
        r'/[0-9]+$',
        # Exclusions
        r'!/subject/created$',
    )

    @tornado.web.authenticated
    @gen.coroutine
    def get(self, activity_id):
        if activity_id == '':
            yield self.query()

        raise errors.MethodError("GET for single activity is not implemented")

    @gen.coroutine
    def query(self):
        until_date = self.get_argument('until', '')
        if until_date != '':
            until_date = datetime.datetime.fromtimestamp(float(until_date))
        else:
            until_date = datetime.datetime.utcnow()

        period = self.get_argument('period', '')
        if period != '':
            period = datetime.timedelta(seconds=float(period))
        else:
            period = datetime.timedelta(days=7)

        if period.days > 31:
            raise errors.ModelError("Time period is too large")

        from_date = until_date - period

        # Only show sticky elements when viewing current time period
        offset = abs((until_date - datetime.datetime.utcnow()).total_seconds())
        include_sticky = offset < period.total_seconds() / 2

        son, details = yield self.fetch_activities(
            from_date, until_date, include_sticky)

        for i, message in enumerate(details):
            self.add_header('Profiling', "%d %s" % (i, message))

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @run_on_executor
    def fetch_activities(self, from_date, until_date, include_sticky):
        start_super = perf()
        timing = []
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            act = Activities(session)
            sticky_flags = {'filter'}
            if include_sticky:
                sticky_flags.update({'include', 'at_top'})

            start = perf()
            query = act.timeline_query(
                user_session.user.id, from_date, until_date,
                sticky_flags=sticky_flags)
            duration = perf() - start
            timing.append("Query construction took %gs" % duration)

            start = perf()
            activities = query.all()
            duration = perf() - start
            timing.append("Query execution took %gs" % duration)

            # Use hand-written serialisation code, because the reflection done
            # in ToSon is too slow for this large number of items.
            # (5ms vs 300ms)
            start = perf()
            user_sons = {}
            activity_sons = []
            for a in activities:
                a_son = {
                    'id': str(a.id),
                    'created': a.created.timestamp(),
                    'message': a.message,
                    'obIds': [str(id_) for id_ in a.ob_ids],
                    'obType': a.ob_type,
                    'sticky': a.sticky,
                    'verbs': list(a.verbs),
                }
                user = a.subject
                if user in user_sons:
                    user_son = user_sons[user]
                else:
                    user_son = {
                        'id': str(user.id),
                        'name': user.name,
                    }
                    user_sons[a.subject] = user_son

                if a.ob_type == 'organisation':
                    a_son['org_id'] = str(a.ob_ids[0])

                a_son['subject'] = user_son
                activity_sons.append(a_son)

            son = {
                'from': from_date.timestamp(),
                'until': until_date.timestamp(),
                'actions': activity_sons
            }
            duration = perf() - start
            timing.append("Serialization took %gs" % duration)

        duration = perf() - start_super
        timing.append("Total: %gs" % duration)

        return son, timing

    @tornado.web.authenticated
    def post(self, activity_id):
        if activity_id:
            raise errors.ModelError("Can't specify ID for new activity")

        if len(self.request_son['message']) < 3:
            raise errors.ModelError("Message is too short")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            if self.request_son['to'] == 'org':
                ob = user_session.org
                if not ob:
                    raise errors.ModelError('No such organisation')
            elif self.request_son['to'] == 'all':
                ob = None
            else:
                raise errors.ModelError('Unrecognised recipient')

            activity = model.Activity(
                subject_id=user_session.user.id,
                verbs=['broadcast'],
                message=self.request_son['message'],
                sticky=self.request_son['sticky']
            )

            if ob:
                desc = ob.action_descriptor
                activity.ob_type = desc.ob_type
                activity.ob_ids = desc.ob_ids
                activity.ob_refs = desc.ob_refs
            else:
                activity.ob_type = None
                activity.ob_ids = []
                activity.ob_refs = []

            session.add(activity)
            session.flush()

            policy = user_session.policy.derive({
                'activity': activity,
                'org': activity.subject.organisation,
            })
            policy.verify('post_add')

            son = ActivityHandler.TO_SON(activity)

            act = Activities(session)
            if ob and not act.has_subscription(user_session.user, ob):
                act.subscribe(user_session.user, ob)
                self.reason("Subscribed to " + ob.ob_type)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def put(self, activity_id):
        with model.session_scope() as session:
            activity = (
                session.query(model.Activity)
                .get(activity_id))
            if not activity:
                raise errors.MissingDocError("No such activity")

            user_session = self.get_user_session(session)
            policy = user_session.policy.derive({
                'activity': activity,
                'org': activity.subject.organisation,
            })

            if 'sticky' in self.request_son:
                if self.request_son.sticky != activity.sticky:
                    policy.verify('post_pin')
                    activity.sticky = self.request_son.sticky

            if 'message' in self.request_son:
                if self.request_son.message != activity.message:
                    policy.verify('post_edit')
                    activity.message = self.request_son.message

            son = ActivityHandler.TO_SON(activity)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def delete(self, activity_id):
        with model.session_scope() as session:
            activity = (
                session.query(model.Activity)
                .get(activity_id))
            if not activity:
                raise errors.MissingDocError("No such activity")

            user_session = self.get_user_session(session)
            policy = user_session.policy.derive({
                'activity': activity,
                'org': activity.subject.organisation,
            })
            policy.verify('post_del')

            session.delete(activity)

        self.set_header("Content-Type", "text/plain")
        self.write("Deleted")
        self.finish()


class SubscriptionHandler(base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self, ob_type, ids):
        if ob_type:
            self.query(ob_type, ids.split(','))
            return

        subscription_id = ids
        with model.session_scope() as session:
            subscription = (
                session.query(model.Subscription)
                .get(subscription_id))
            if not subscription:
                raise errors.MissingDocError("No such subscription")

            user_session = self.get_user_session(session)
            policy = user_session.policy.derive({
                'user': subscription.user,
            })
            policy.verify('subscription_view')

            to_son = ToSon(
                r'/created$',
                r'/user_id$',
                r'/subscribed$',
                r'/ob_type$',
                r'/ob_refs/?.*$',
            )
            son = to_son(subscription)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self, ob_type, object_ids):
        with model.session_scope() as session:
            ob = self.get_ob(session, ob_type, object_ids)
            if not ob:
                raise errors.MissingDocError("No such object")

            user_session = self.get_user_session(session)
            act = Activities(session)
            subscription_map = {
                tuple(sub.ob_refs): sub.subscribed
                for sub in act.subscriptions(user_session.user, ob)}
            subscription_id_map = {
                tuple(sub.ob_refs): sub.id
                for sub in act.subscriptions(user_session.user, ob)}

            lineage = [{
                'id': subscription_id_map.get(tuple(item.ob_ids), None),
                'title': item.ob_title,
                'ob_type': item.ob_type,
                'ob_ids': item.ob_ids,
                'subscribed': subscription_map.get(tuple(item.ob_ids), None)
            } for item in ob.action_lineage]

            to_son = ToSon(
                r'/id$',
                r'/title$',
                r'/subscribed$',
                r'/ob_type$',
                r'/ob_ids/?.*$',
                r'/[0-9]+$',
            )
            sons = to_son(lineage)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @tornado.web.authenticated
    def post(self, ob_type, object_ids):
        object_ids = object_ids.split(',')
        log.error("%s", object_ids)

        if not ob_type:
            raise errors.ModelError(
                "Object type required when creating a subscription")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            ob = self.get_ob(session, ob_type, object_ids)
            if not ob:
                raise errors.MissingDocError("No such object")

            act = Activities(session)
            subscription = act.subscribe(user_session.user, ob)
            subscription.subscribed = self.request_son.get(
                'subscribed', False)

            policy = user_session.policy.derive({
                'user': subscription.user,
                'survey': self.get_survey(ob),
                'submission': self.get_submission(ob),
            })
            policy.verify('subscription_add')

            session.flush()
            subscription_id = str(subscription.id)

        self.get('', subscription_id)

    @tornado.web.authenticated
    def put(self, ob_type, subscription_id):
        if ob_type:
            raise errors.ModelError(
                "Can't provide object type when updating a subscription")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            subscription = (
                session.query(model.Subscription)
                .get(subscription_id))

            if not subscription:
                raise errors.MissingDocError("No such subscription")

            subscription.subscribed = self.request_son.get('subscribed', False)

            ob = self.get_ob(
                session, subscription.ob_type, subscription.ob_refs)
            policy = user_session.policy.derive({
                'user': subscription.user,
                'survey': self.get_survey(ob),
                'submission': self.get_submission(ob),
            })
            policy.verify('subscription_edit')

            subscription_id = str(subscription.id)

        self.get('', subscription_id)

    @tornado.web.authenticated
    def delete(self, ob_type, subscription_id):
        if ob_type:
            raise errors.ModelError(
                "Can't provide object type when deleting a subscription")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            subscription = (
                session.query(model.Subscription)
                .get(subscription_id))

            if not subscription:
                raise model.MissingDocError("No subscription for that object")

            policy = user_session.policy.derive({
                'user': subscription.user,
            })
            policy.verify('subscription_del')

            session.delete(subscription)

        self.finish()

    def get_ob(self, session, ob_type, ob_refs):
        def arglen(n, min_, max_=None):
            if max_ is None:
                max_ = min_
            if len(ob_refs) < min_ or len(ob_refs) > max_:
                raise errors.ModelError(
                    "Wrong number of IDs for %s" % ob_type)

        if ob_type == 'custom_query':
            arglen(len(ob_refs), 1)
            query = (
                session.query(model.CustomQuery)
                .filter(model.CustomQuery.id == ob_refs[0]))

        elif ob_type == 'organisation':
            arglen(len(ob_refs), 1)
            query = (
                session.query(model.Organisation)
                .filter(model.Organisation.id == ob_refs[0]))

        elif ob_type == 'user':
            arglen(len(ob_refs), 1)
            query = (
                session.query(model.AppUser)
                .filter(model.AppUser.id == ob_refs[0]))

        elif ob_type == 'program':
            arglen(len(ob_refs), 1)
            query = (
                session.query(model.Program)
                .filter(model.Program.id == ob_refs[0]))

        elif ob_type == 'survey':
            arglen(len(ob_refs), 2, 2)
            query = (
                session.query(model.Survey)
                .filter(model.Survey.id == ob_refs[0],
                        model.Survey.program_id == ob_refs[1]))

        elif ob_type == 'qnode':
            arglen(len(ob_refs), 2, 2)
            query = (
                session.query(model.QuestionNode)
                .filter(model.QuestionNode.id == ob_refs[0],
                        model.QuestionNode.program_id == ob_refs[1]))

        elif ob_type == 'measure':
            arglen(len(ob_refs), 2, 2)
            query = (
                session.query(model.Measure)
                .filter(model.Measure.id == ob_refs[0],
                        model.Measure.program_id == ob_refs[1]))

        elif ob_type == 'response_type':
            arglen(len(ob_refs), 2, 2)
            query = (
                session.query(model.ResponseType)
                .filter(model.ResponseType.id == ob_refs[0],
                        model.ResponseType.program_id == ob_refs[1]))

        elif ob_type == 'submission':
            arglen(len(ob_refs), 1)
            query = (
                session.query(model.Submission)
                .filter(model.Submission.id == ob_refs[0]))

        elif ob_type == 'rnode':
            arglen(len(ob_refs), 2, 2)
            query = (
                session.query(model.ResponseNode)
                .filter(model.ResponseNode.qnode_id == ob_refs[0],
                        model.ResponseNode.submission_id == ob_refs[1]))

        elif ob_type == 'response':
            arglen(len(ob_refs), 2, 2)
            query = (
                session.query(model.Response)
                .filter(model.Response.measure_id == ob_refs[0],
                        model.Response.submission_id == ob_refs[1]))

        else:
            raise errors.ModelError("Can't subscribe to '%s' type" % ob_type)

        return query.first()

    def get_survey(self, ob):
        if ob.ob_type not in {'survey', 'qnode', 'measure'}:
            return None
        if hasattr(ob, 'survey'):
            return ob.survey
        return ob

    def get_submission(self, ob):
        if ob.ob_type not in {'submission', 'rnode', 'response'}:
            return None
        if hasattr(ob, 'submission'):
            return ob.submission
        return ob

    def update(self, subscription, son):
        '''
        Apply user-provided data to the saved model.
        '''
        update = updater(subscription, error_factory=errors.ModelError)
        update('subscribed', son)


class CardHandler(base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self):
        sons = []
        to_son = ToSon(
            r'.*'
        )
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            org = user_session.org
            sons.append(to_son({
                'title': org.name,
                'created': org.created,
                'ob_type': 'organisation',
                'ob_ids': [org.id],
            }))

            if user_session.has_role('author', 'consultant'):
                programs = (
                    session.query(model.Program)
                    .filter(model.Program.finalised_date == None)
                    .order_by(model.Program.created.desc())
                    .limit(2)
                    .all())
                sons += to_son([{
                    'title': s.title,
                    'created': s.created,
                    'ob_type': 'program',
                    'ob_ids': [s.id],
                } for s in programs])

            if user_session.has_role('clerk'):
                submissions = (
                    session.query(model.Submission)
                    .filter(model.Submission.organisation_id == org.id)
                    .order_by(model.Submission.created.desc())
                    .limit(2)
                    .all())
                sons += to_son([{
                    'title': a.title,
                    'created': a.created,
                    'ob_type': 'submission',
                    'ob_ids': [a.id],
                } for a in submissions])

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()
