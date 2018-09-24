import urllib.parse

from tornado.escape import json_decode, json_encode
from tornado.httpclient import AsyncHTTPClient
import tornado.gen
import tornado.web
import sqlalchemy
from sqlalchemy.orm import joinedload

from activity import Activities
import base_handler
import errors
import model

from cache import LruCache
from surveygroup_actions import assign_surveygroups, filter_surveygroups
from utils import ToSon, truthy, updater


class OrgHandler(base_handler.Paginate, base_handler.BaseHandler):
    @tornado.web.authenticated
    def get(self, organisation_id):
        if organisation_id == "":
            self.query()
            return

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            org = (
                session.query(model.Organisation)
                .options(joinedload('surveygroups'))
                .get(organisation_id))
            if not org:
                raise errors.MissingDocError("No such organisation")

            policy = user_session.policy.derive({
                'org': org,
                'surveygroups': org.surveygroups,
            })
            policy.verify('org_view')

            # Check that user shares a common surveygroup with this org.
            # Admins need access to orgs outside their surveygroups though.
            if not policy.check('admin'):
                policy.verify('surveygroup_interact')

            to_son = ToSon(
                r'/id$',
                r'/name$',
                r'/title$',
                r'/deleted$',
                r'/url$',
                r'/locations.*$',
                r'/meta.*$',
                r'/[0-9+]$',
            )
            to_son.exclude(
                r'/locations/.*/organisation(_id)?$',
                r'/locations/.*/id$',
                r'/meta/organisation(_id)?$',
                r'/meta/id$',
            )
            if policy.check('surveygroup_browse'):
                to_son.add(r'^/surveygroups$')
            son = to_son(org)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        sons = []
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            policy = user_session.policy.derive({})
            policy.verify('org_browse')

            query = session.query(model.Organisation)

            # Filter out orgs that don't share a surveygroup with this user.
            # Admins need access to orgs outside their surveygroups though.
            if not policy.check('admin'):
                query = filter_surveygroups(
                    session, query, user_session.user.id,
                    [], [model.organisation_surveygroup])

            # Filter down to just organisations in a particular survey group
            surveygroup_id = self.get_argument("surveyGroupId", None)
            if surveygroup_id:
                query = (
                    query.join(model.SurveyGroup, model.Organisation.surveygroups)
                    .filter(model.SurveyGroup.id == surveygroup_id))

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.Organisation.name.ilike(r'%{}%'.format(term)))

            deleted = self.get_argument('deleted', '')
            if deleted != '':
                deleted = truthy(deleted)
                query = query.filter(model.Organisation.deleted == deleted)

            query = query.order_by(model.Organisation.name)
            query = self.paginate(query)

            to_son = ToSon(
                r'^/[0-9]+/id$',
                r'/name$',
                r'/deleted$',
                r'/locations$',
                r'/locations/0/description$',
                r'/meta$',
                r'/meta/asset_types.*$',
                # Descend into list
                r'/[0-9]+$'
            )
            sons = to_son(query.all())
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @tornado.web.authenticated
    def post(self, organisation_id):
        '''
        Create a new organisation.
        '''
        if organisation_id:
            raise errors.MethodError(
                "Can't use POST for existing organisation.")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            org = model.Organisation()

            try:
                assign_surveygroups(user_session, org, self.request_son)
            except ValueError as e:
                raise errors.ModelError(str(e))

            self._update(org, self.request_son)
            session.add(org)

            # Need to flush so object has an ID to record action against.
            session.flush()

            policy = user_session.policy.derive({
                'org': org,
                'surveygroups': org.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('org_add')

            act = Activities(session)
            act.record(user_session.user, org, ['create'])
            act.ensure_subscription(user_session.user, org, org, self.reason)

            organisation_id = str(org.id)
        self.get(organisation_id)

    @tornado.web.authenticated
    def put(self, organisation_id):
        '''
        Update an existing organisation.
        '''
        if not organisation_id:
            raise errors.MethodError(
                "Can't use PUT for new organisations (no ID).")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            org = session.query(model.Organisation).get(organisation_id)
            if not org:
                raise errors.MissingDocError("No such organisation")

            try:
                groups_changed = assign_surveygroups(
                    user_session, org, self.request_son)
            except ValueError as e:
                raise errors.ModelError(str(e))

            policy = user_session.policy.derive({
                'org': org,
                'surveygroups': org.surveygroups,
            })
            policy.verify('org_edit')

            # Check that user shares a common surveygroup with this org.
            # Admins need permission to edit orgs outside their surveygroups
            # though.
            if not policy.check('admin'):
                policy.verify('surveygroup_interact')

            old_locations = list(org.locations)
            self._update(org, self.request_son)

            verbs = []
            if (session.is_modified(org) or
                    org.locations != old_locations or
                    groups_changed or
                    session.is_modified(org.meta)):
                verbs.append('update')

            if org.deleted:
                org.deleted = False
                verbs.append('undelete')

            act = Activities(session)
            act.record(user_session.user, org, verbs)
            act.ensure_subscription(user_session.user, org, org, self.reason)

        self.get(organisation_id)

    @tornado.web.authenticated
    def delete(self, organisation_id):
        if not organisation_id:
            raise errors.MethodError("Organisation ID required")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            org = session.query(model.Organisation).get(organisation_id)
            if not org:
                raise errors.MissingDocError("No such organisation")

            policy = user_session.policy.derive({
                'org': org,
                'surveygroups': org.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('org_del')

            act = Activities(session)
            if not org.deleted:
                act.record(user_session.user, org, ['delete'])
            act.ensure_subscription(user_session.user, org, org, self.reason)

            org.deleted = True

        self.finish()

    def _update(self, org, son):
        '''
        Apply user-provided data to the saved model.
        '''
        update = updater(org, error_factory=errors.ModelError)
        update('name', son)
        update('url', son)
        self._save_locations(org, son.get('locations', []))
        self._save_meta(org, son.get('meta', {}))

    def _save_locations(self, org, sons):
        column_names = {c.name
                        for c in sqlalchemy.inspect(model.OrgLocation).columns
                        if c.name not in {'id', 'organisation_id'}}

        def loc_eq(a, b):
            return all(a.get(n, None) == getattr(b, n) for n in column_names)

        locs = []
        for l in sons:
            # Try to find an existing location object that matches the one
            # provided by the user
            matching_locs = [l_existing for l_existing in org.locations
                             if loc_eq(l, l_existing)]
            if len(matching_locs) > 0:
                locs.append(matching_locs[0])
                continue

            # No match, so create a new one
            l = {k: l[k]
                 for k in l
                 if k in column_names}
            locs.append(model.OrgLocation(**l))

        # Replace locations collection. The relationship will automatically
        # delete old locations that are no longer referenced.
        org.locations = locs

    def _save_meta(self, org, son):
        column_names = {c.name
                        for c in sqlalchemy.inspect(model.OrgMeta).columns
                        if c.name not in {'id', 'organisation_id'}}
        if not org.meta:
            org.meta = model.OrgMeta()
        for n in column_names:
            setattr(org.meta, n, son.get(n))


class PurchasedSurveyHandler(base_handler.BaseHandler):

    @tornado.web.authenticated
    def head(self, organisation_id, survey_id):
        program_id = self.get_argument('programId', '')

        with model.session_scope() as session:
            org = session.query(model.Organisation).get(organisation_id)
            if not org:
                raise errors.MissingDocError("No such organisation")

            survey = (
                session.query(model.Survey)
                .get((survey_id, program_id)))
            if not survey:
                raise errors.MissingDocError("No such survey")

            user_session = self.get_user_session(session)
            policy = user_session.policy.derive({
                'org': org,
                'surveygroups': survey.surveygroups & org.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('submission_browse')

            purchased_survey = (
                session.query(model.PurchasedSurvey)
                .get((program_id, survey_id, organisation_id)))
            if not purchased_survey:
                raise errors.MissingDocError(
                    "This survey has not been purchased yet")

        self.finish()

    @tornado.web.authenticated
    def get(self, organisation_id, survey_id):
        if not survey_id:
            self.query(organisation_id)

        raise errors.ModelError("Not implemented")

    def query(self, organisation_id):
        deleted = self.get_argument('deleted', '')
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            org = session.query(model.Organisation).get(organisation_id)
            if not org:
                raise errors.MissingDocError("No such organisation")

            policy = user_session.policy.derive({
                'org': org,
                'surveygroups': org.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('submission_browse')

            query = (
                session.query(model.Survey)
                .join(model.PurchasedSurvey)
                .filter(
                    model.PurchasedSurvey.organisation_id == organisation_id))

            if deleted:
                deleted = truthy(deleted)
                if deleted:
                    del_filter = ((model.Survey.deleted == True) |
                                  (model.Program.deleted == True))
                else:
                    del_filter = ((model.Survey.deleted == False) &
                                  (model.Program.deleted == False))
                query = query.join(model.Program).filter(del_filter)

            if not policy.check('surveygroup_interact_all'):
                query = filter_surveygroups(
                    session, query, user_session.user.id,
                    [model.Program], [model.program_surveygroup])

            surveys = query.all()

            to_son = ToSon(
                r'/id$',
                r'/title$',
                r'/deleted$',
                r'/n_measures$',
                r'/program/tracking_id$',
                # Descend into list
                r'/[0-9]+$',
                r'/program$'
            )

            sons = to_son(surveys)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @tornado.web.authenticated
    def put(self, organisation_id, survey_id):
        program_id = self.get_argument('programId', '')

        with model.session_scope() as session:
            org = session.query(model.Organisation).get(organisation_id)
            if not org:
                raise errors.MissingDocError("No such organisation")
            survey = (
                session.query(model.Survey)
                .get((survey_id, program_id)))
            if not survey:
                raise errors.MissingDocError('No such survey')

            user_session = self.get_user_session(session)
            policy = user_session.policy.derive({
                'org': org,
                'survey': survey,
                'surveygroups': survey.surveygroups & org.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('survey_purchase')

            purchased_survey = (
                session.query(model.PurchasedSurvey)
                .get((program_id, survey_id, org.id)))

            if not purchased_survey:
                org.surveys.append(survey)

    @tornado.web.authenticated
    def delete(self, organisation_id, survey_id):
        program_id = self.get_argument('programId', '')

        with model.session_scope() as session:
            org = session.query(model.Organisation).get(organisation_id)
            if not org:
                raise errors.MissingDocError('No such organisation')
            survey = (
                session.query(model.Survey)
                .get((survey_id, program_id)))
            if not survey:
                raise errors.MissingDocError('No such survey')

            user_session = self.get_user_session(session)
            policy = user_session.policy.derive({
                'org': org,
                'survey': survey,
                'surveygroups': survey.surveygroups & org.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('survey_purchase')

            org.programs.remove(survey)


class LocationSearchHandler(base_handler.BaseHandler):
    search_headers = {
        'headers': {
            'accept-language': 'en-AU,en;q=0.9,en-GB;q=0.8,en-US;q=0.7'
        }
    }
    cache = LruCache()

    @tornado.gen.coroutine
    def get(self, search_str):
        if search_str not in self.cache:
            locations = yield self.location_search(search_str)
            self.cache[search_str] = locations
        else:
            locations = self.cache[search_str]

        self.set_header('Content-Type', 'application/json')
        self.write(json_encode(locations))

    @tornado.gen.coroutine
    def location_search(self, search_str):
        search_parm = urllib.parse.quote(search_str, safe='')
        url = ('https://nominatim.openstreetmap.org/search/{}?'
               'format=json&addressdetails=1&limit=7'
               .format(search_parm))
        client = AsyncHTTPClient()
        response = yield client.fetch(url, **LocationSearchHandler.search_headers)
        nominatim = json_decode(response.body)

        locations = []
        for nom in nominatim:
            if nom['type'] in {'political'}:
                continue

            a = nom['address']
            try:
                lon = float(nom['lon'])
                lat = float(nom['lat'])
            except (KeyError, ValueError):
                lon = None
                lat = None

            location = {
                'description': nom['display_name'],
                'licence': nom['licence'],
                'lon': lon,
                'lat': lat,
                'country': a.get('country'),
                'region': a.get('region') or a.get('state_district'),
                'state': a.get('state'),
                'county': a.get('county'),
                'postcode': a.get('postcode'),
                'city': a.get('city') or a.get('town'),
                'suburb': a.get('suburb'),
            }
            locations.append(location)

        return locations
