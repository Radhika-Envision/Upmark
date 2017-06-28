import urllib.parse

from tornado.escape import json_decode, json_encode
from tornado.httpclient import AsyncHTTPClient
import tornado.gen
import tornado.web
import sqlalchemy

from activity import Activities
import auth
import base_handler
import crud.program
import errors
import model

from cache import LruCache
from utils import ToSon, truthy, updater


class OrgHandler(base_handler.Paginate, base_handler.BaseHandler):
    @tornado.web.authenticated
    def get(self, organisation_id):
        if organisation_id == "":
            self.query()
            return

        with model.session_scope() as session:
            try:
                org = session.query(model.Organisation).get(organisation_id)
                if org is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise errors.MissingDocError("No such organisation")

            policy = self.authz_policy.derive({'org': org})
            policy.verify('org_view')

            to_son = ToSon(
                r'/id$',
                r'/name$',
                r'/deleted$',
                r'/url$',
                r'/locations.*$',
                r'/meta.*$',
            )
            to_son.exclude(
                r'/locations/.*/organisation(_id)?$',
                r'/locations/.*/id$',
                r'/meta/organisation(_id)?$',
                r'/meta/id$',
            )
            son = to_son(org)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        self.authz_policy.verify('org_browse')

        sons = []
        with model.session_scope() as session:
            query = session.query(model.Organisation)
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
        if organisation_id != '':
            raise errors.MethodError(
                "Can't use POST for existing organisation.")

        self.authz_policy.verify('org_add')

        try:
            with model.session_scope() as session:
                org = model.Organisation()
                self._update(org, self.request_son)
                session.add(org)

                # Need to flush so object has an ID to record action against.
                session.flush()

                act = Activities(session)
                act.record(self.current_user, org, ['create'])
                if not act.has_subscription(self.current_user, org):
                    act.subscribe(self.current_user, org)
                    self.reason("Subscribed to organisation")

                organisation_id = str(org.id)
        except sqlalchemy.exc.IntegrityError as e:
            raise errors.ModelError.from_sa(e)
        self.get(organisation_id)

    @tornado.web.authenticated
    def put(self, organisation_id):
        '''
        Update an existing organisation.
        '''
        if organisation_id == '':
            raise errors.MethodError(
                "Can't use PUT for new organisations (no ID).")

        try:
            with model.session_scope() as session:
                org = session.query(model.Organisation).get(organisation_id)
                if org is None:
                    raise ValueError("No such object")

                policy = self.authz_policy.derive({'org': org})
                policy.verify('org_edit')

                old_locations = list(org.locations)
                self._update(org, self.request_son)

                verbs = []
                if (session.is_modified(org)
                        or org.locations != old_locations
                        or session.is_modified(org.meta)):
                    verbs.append('update')

                if org.deleted:
                    org.deleted = False
                    verbs.append('undelete')

                act = Activities(session)
                act.record(self.current_user, org, verbs)
                if not act.has_subscription(self.current_user, org):
                    act.subscribe(self.current_user, org)
                    self.reason("Subscribed to organisation")

        except sqlalchemy.exc.IntegrityError as e:
            raise errors.ModelError.from_sa(e)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise errors.MissingDocError("No such organisation")
        self.get(organisation_id)

    @tornado.web.authenticated
    def delete(self, organisation_id):
        if organisation_id == '':
            raise errors.MethodError("Organisation ID required")
        try:
            with model.session_scope() as session:
                org = session.query(model.Organisation).get(organisation_id)
                if org is None:
                    raise errors.MissingDocError("No such organisation")

                policy = self.authz_policy.derive({'org': org})
                policy.verify('org_del')

                act = Activities(session)
                if not org.deleted:
                    act.record(self.current_user, org, ['delete'])
                if not act.has_subscription(self.current_user, org):
                    act.subscribe(self.current_user, org)
                    self.reason("Subscribed to organisation")

                org.deleted = True

        except (sqlalchemy.exc.StatementError, ValueError):
            raise errors.MissingDocError("No such organisation")

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


class PurchasedSurveyHandler(crud.program.ProgramCentric, base_handler.BaseHandler):
    @tornado.web.authenticated
    def head(self, organisation_id, survey_id):
        with model.session_scope() as session:
            org = session.query(model.Organisation).get(organisation_id)
            if org is None:
                raise errors.MissingDocError("No such organisation")

            policy = self.authz_policy.derive({'org': org})
            policy.verify('submission_browse')

            purchased_survey = (session.query(model.PurchasedSurvey)
                .filter_by(program_id=self.program_id,
                           survey_id=survey_id,
                           organisation_id=organisation_id)
                .first())
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
            org = session.query(model.Organisation).get(organisation_id)
            if org is None:
                raise errors.MissingDocError("No such organisation")

            policy = self.authz_policy.derive({'org': org})
            policy.verify('submission_browse')

            query = (session.query(model.Survey)
                .join(model.PurchasedSurvey)
                .filter(model.PurchasedSurvey.organisation_id == organisation_id))

            if deleted:
                deleted = truthy(deleted)
                if deleted:
                    del_filter = ((model.Survey.deleted == True) |
                                  (model.Program.deleted == True))
                else:
                    del_filter = ((model.Survey.deleted == False) &
                                  (model.Program.deleted == False))
                query = query.join(model.Program).filter(del_filter)

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
        with model.session_scope() as session:
            org = session.query(model.Organisation).get(organisation_id)
            if org is None:
                raise errors.MissingDocError("No such organisation")
            survey = (session.query(model.Survey)
                .get((survey_id, self.program_id)))
            if not survey:
                raise errors.MissingDocError('No such survey')

            policy = self.authz_policy.derive({
                'org': org,
                'survey': survey,
            })
            policy.verify('survey_purchase')

            purchased_survey = (session.query(model.PurchasedSurvey)
                .get((self.program_id, survey_id, org.id)))

            if not purchased_survey:
                org.surveys.append(survey)

    @tornado.web.authenticated
    def delete(self, organisation_id, program_id):
        with model.session_scope() as session:
            org = session.query(model.Organisation).get(organisation_id)
            if not org:
                raise errors.MissingDocError('No such organisation')
            survey = (session.query(model.Survey)
                .get((survey_id, self.program_id)))
            if not survey:
                raise errors.MissingDocError('No such survey')

            policy = self.authz_policy.derive({
                'org': org,
                'survey': survey,
            })
            policy.verify('survey_purchase')

            org.programs.remove(survey)


class LocationSearchHandler(base_handler.BaseHandler):
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
        response = yield client.fetch(url)
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
