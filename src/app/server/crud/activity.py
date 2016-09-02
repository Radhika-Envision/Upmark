from concurrent.futures import ThreadPoolExecutor
import datetime
import logging
import time

from tornado import gen
from tornado.concurrent import run_on_executor
from tornado.escape import json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.orm import defer, noload, joinedload

from activity import Activities
import handlers
import model
from utils import ToSon, truthy, updater


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


class ActivityHandler(handlers.BaseHandler):

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    TO_SON = ToSon(
        r'/id$',
        r'/created$',
        r'/message$',
        r'/sticky$',
        r'/subject$',
        r'/subject/name$',
        r'/verbs/?.*$',
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

        raise handlers.MethodError("GET for single activity is not implemented")

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
            raise handlers.ModelError("Time period is too large")

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
            act = Activities(session)
            sticky_flags = {'filter'}
            if include_sticky:
                sticky_flags.update({'include', 'at_top'})

            start = perf()
            query = act.timeline_query(
                self.current_user.id, from_date, until_date,
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
        if activity_id != '':
            raise handlers.ModelError("Can't specify ID for new activity")

        if len(self.request_son['message']) < 3:
            raise handlers.ModelError("Message is too short")

        with model.session_scope() as session:
            if self.request_son['to'] == 'org':
                self.check_privillege('org_admin')
                ob = (session.query(model.Organisation)
                    .get(self.current_user.organisation_id))
                if ob is None:
                    raise handlers.ModelError('No such organisation')
            elif self.request_son['to'] == 'all':
                self.check_privillege('admin')
                ob = None
            else:
                raise handlers.ModelError('Unrecognised recipient')

            activity = model.Activity(
                subject_id=self.current_user.id,
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
            self.check_create(activity)
            son = ActivityHandler.TO_SON(activity)

            act = Activities(session)
            if ob and not act.has_subscription(self.current_user, ob):
                act.subscribe(self.current_user, ob)
                self.reason("Subscribed to " + ob.ob_type)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def put(self, activity_id):
        with model.session_scope() as session:
            activity = (session.query(model.Activity)
                .get(activity_id))
            if not activity:
                raise handlers.MissingDocError("No such activity")

            self.check_modify(activity)

            if 'sticky' in self.request_son:
                activity.sticky = self.request_son['sticky']
            if 'message' in self.request_son:
                activity.message = self.request_son['message']
            son = ActivityHandler.TO_SON(activity)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def delete(self, activity_id):
        with model.session_scope() as session:
            activity = (session.query(model.Activity)
                .get(activity_id))
            if not activity:
                raise handlers.MissingDocError("No such activity")
            self.check_delete(activity)
            session.delete(activity)

        self.set_header("Content-Type", "text/plain")
        self.write("Deleted")
        self.finish()

    def check_create(self, activity):
        if activity.verbs != ['broadcast']:
            raise handlers.AuthzError(
                "You can't create a non-broadcast activity")
        self.check_modify(activity)

    def check_modify(self, activity):
        if self.has_privillege('admin'):
            return
        elif self.has_privillege('org_admin'):
            org = activity.subject.organisation
            if str(org.id) != str(self.current_user.organisation_id):
                raise handlers.AuthzError(
                    "You can't modify another organisation's activity")
        else:
            raise handlers.AuthzError(
                "You can't modify activities")

    def check_delete(self, activity):
        if activity.verbs != ['broadcast']:
            raise handlers.AuthzError(
                "You can't delete a non-broadcast activity")
        self.check_modify(activity)


class SubscriptionHandler(handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, ob_type, ids):
        if ob_type != '':
            self.query(ob_type, ids.split(','))
            return

        subscription_id = ids
        with model.session_scope() as session:
            subscription = (session.query(model.Subscription)
                .get(subscription_id))
            if not subscription:
                raise handlers.MissingDocError("No such subscription")

            if subscription.user_id != self.current_user.id:
                raise handlers.ModelError(
                    "Can't view another user's subscriptions")

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
                raise handlers.MissingDocError("No such object")

            act = Activities(session)
            subs = act.subscriptions(self.current_user, ob)
            subscription_map = {
                tuple(sub.ob_refs): sub.subscribed
                for sub in act.subscriptions(self.current_user, ob)}
            subscription_id_map = {
                tuple(sub.ob_refs): sub.id
                for sub in act.subscriptions(self.current_user, ob)}

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

        if ob_type == '':
            raise handlers.ModelError(
                "Object type required when creating a subscription")

        try:
            with model.session_scope() as session:
                ob = self.get_ob(session, ob_type, object_ids)
                if not ob:
                    raise handlers.MissingDocError("No such object")

                act = Activities(session)
                subscription = act.subscribe(self.current_user, ob)
                subscription.subscribed = self.request_son.get(
                    'subscribed', False)
                if subscription.subscribed:
                    user = (session.query(model.AppUser)
                        .get(self.current_user.id))
                    self.check_subscribe_authz(user, ob)

                session.flush()
                subscription_id = str(subscription.id)

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)

        self.get('', subscription_id)

    @tornado.web.authenticated
    def put(self, ob_type, subscription_id):
        if ob_type != '':
            raise handlers.ModelError(
                "Can't provide object type when updating a subscription")

        with model.session_scope() as session:
            subscription = (session.query(model.Subscription)
                .get(subscription_id))

            if not subscription:
                raise handlers.MissingDocError("No such subscription")

            if subscription.user_id != self.current_user.id:
                raise handlers.AuthzError(
                    "You can't modify another user's subscriptions")

            subscription.subscribed = self.request_son.get('subscribed', False)
            if subscription.subscribed:
                user = session.query(model.AppUser).get(self.current_user.id)
                ob = self.get_ob(
                    session, subscription.ob_type, subscription.ob_refs)
                self.check_subscribe_authz(user, ob)

            subscription_id = str(subscription.id)

        self.get('', subscription_id)

    @tornado.web.authenticated
    def delete(self, ob_type, subscription_id):
        if ob_type != '':
            raise handlers.ModelError(
                "Can't provide object type when deleting a subscription")

        with model.session_scope() as session:
            subscription = (session.query(model.Subscription)
                .get(subscription_id))

            if not subscription:
                raise model.MissingDocError("No subscription for that object")

            if subscription.user_id != self.current_user.id:
                raise handlers.AuthzError(
                    "You can't modify another user's subscriptions")

            session.delete(subscription)

        self.finish()

    def get_ob(self, session, ob_type, ob_refs):
        def arglen(n, min_, max_=None):
            if max_ is None:
                max_ = min_
            if len(ob_refs) < min_ or len(ob_refs) > max_:
                raise handlers.ModelError(
                    "Wrong number of IDs for %s" % ob_type)

        if ob_type == 'organisation':
            arglen(len(ob_refs), 1)
            query = (session.query(model.Organisation)
                .filter(model.Organisation.id == ob_refs[0]))

        elif ob_type == 'user':
            arglen(len(ob_refs), 1)
            query = (session.query(model.AppUser)
                .filter(model.AppUser.id == ob_refs[0]))

        elif ob_type == 'program':
            arglen(len(ob_refs), 1)
            query = (session.query(model.Program)
                .filter(model.Program.id == ob_refs[0]))

        elif ob_type == 'survey':
            arglen(len(ob_refs), 2, 2)
            query = (session.query(model.Survey)
                .filter(model.Survey.id == ob_refs[0],
                        model.Survey.program_id == ob_refs[1]))

        elif ob_type == 'qnode':
            arglen(len(ob_refs), 2, 2)
            query = (session.query(model.QuestionNode)
                .filter(model.QuestionNode.id == ob_refs[0],
                        model.QuestionNode.program_id == ob_refs[1]))

        elif ob_type == 'measure':
            arglen(len(ob_refs), 2, 2)
            query = (session.query(model.Measure)
                .filter(model.Measure.id == ob_refs[0],
                        model.Measure.program_id == ob_refs[1]))

        elif ob_type == 'submission':
            arglen(len(ob_refs), 1)
            query = (session.query(model.Submission)
                .filter(model.Submission.id == ob_refs[0]))

        elif ob_type == 'rnode':
            arglen(len(ob_refs), 2, 2)
            query = (session.query(model.ResponseNode)
                .filter(model.ResponseNode.qnode_id == ob_refs[0],
                        model.ResponseNode.submission_id == ob_refs[1]))

        elif ob_type == 'response':
            arglen(len(ob_refs), 2, 2)
            query = (session.query(model.Response)
                .filter(model.Response.measure_id == ob_refs[0],
                        model.Response.submission_id == ob_refs[1]))

        else:
            raise handlers.ModelError("Can't subscribe to '%s' type" % ob_type)

        return query.first()

    def check_authz(self, user):
        if self.has_privillege('admin'):
            return
        elif str(user.id) == str(self.current_user.id):
            return
        elif not self.has_privillege('org_admin'):
            raise handlers.AuthzError(
                "You can't access another user's subscriptions.")
        elif str(user.organisation_id) != str(self.current_user.organisation_id):
            raise handlers.AuthzError(
                "You can't access another organisation's user's subscriptions.")

    def check_subscribe_authz(self, user, ob):
        if self.has_privillege('consultant'):
            return

        if ob.ob_type in {'organisation', 'user', 'program'}:
            return
        elif ob.ob_type in {'survey', 'qnode', 'measure'}:
            if hasattr(ob, 'survey'):
                survey = ob.survey
            else:
                survey = ob
            if not survey in user.organisation.purchased_surveys:
                raise handlers.AuthzError(
                    "You can't subscribe to a survey that you haven't"
                    " purchased.")
        elif ob.ob_type in {'submission', 'rnode', 'response'}:
            if hasattr(ob, 'submission'):
                organisation_id = ob.submission.organisation_id
            else:
                organisation_id = ob.organisation_id
            if organisation_id != user.organisation_id:
                raise handlers.AuthzError(
                    "You can't subscribe to another organisation's submission.")

    def update(self, subscription, son):
        '''
        Apply user-provided data to the saved model.
        '''
        update = updater(subscription)
        update('subscribed', son)


class CardHandler(handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self):
        sons = []
        to_son = ToSon(
            r'.*'
        )
        with model.session_scope() as session:
            org_id = self.current_user.organisation_id
            org = (session.query(model.Organisation).get(org_id))
            sons.append(to_son({
                'title': org.name,
                'created': org.created,
                'ob_type': 'organisation',
                'ob_ids': [org.id],
            }))

            if self.has_privillege('author', 'consultant'):
                programs = (session.query(model.Program)
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

            if self.has_privillege('clerk'):
                submissions = (session.query(model.Submission)
                    .filter(model.Submission.organisation_id == org_id)
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
