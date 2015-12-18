import datetime
import time
import uuid
import urllib.parse

from tornado.escape import json_decode, json_encode
from tornado.httpclient import AsyncHTTPClient
import tornado.gen
import tornado.web
import sqlalchemy
from sqlalchemy.orm import joinedload

from activity import Activities
import crud.survey
import handlers
import model
import logging
from utils import LruCache, ToSon, updater

class OrgHandler(handlers.Paginate, handlers.BaseHandler):
    @tornado.web.authenticated
    def get(self, org_id):
        if org_id == "":
            self.query()
            return

        with model.session_scope() as session:
            try:
                org = session.query(model.Organisation).get(org_id)
                if org is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such organisation")

            to_son = ToSon(include=[
                r'/id$',
                r'/name$',
                r'/url$',
                r'/locations.*$',
                r'/meta.*$',
            ], exclude=[
                r'/locations/.*/organisation(_id)?$',
                r'/locations/.*/id$',
                r'/meta/organisation(_id)?$',
                r'/meta/id$',
            ])
            son = to_son(org)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        sons = []
        with model.session_scope() as session:
            query = session.query(model.Organisation)
            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.Organisation.name.ilike(r'%{}%'.format(term)))
            query = query.order_by(model.Organisation.name)
            query = self.paginate(query)

            to_son = ToSon(include=[
                r'/id$',
                r'/name$',
                r'/region$',
                r'/number_of_customers$',
                # Descend into list
                r'/[0-9]+$'
            ])
            sons = to_son(query.all())
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('admin')
    def post(self, org_id):
        '''
        Create a new organisation.
        '''
        if org_id != '':
            raise handlers.MethodError(
                "Can't use POST for existing organisation.")

        try:
            with model.session_scope() as session:
                org = model.Organisation()
                self._update(org, self.request_son)
                session.add(org)
                session.flush()

                act = Activities(session)
                act.record(self.current_user, org, ['create'])
                if not act.has_subscription(self.current_user, org):
                    act.subscribe(self.current_user, org)
                    self.reason("Subscribed to organisation")

                org_id = str(org.id)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(org_id)

    @handlers.authz('admin', 'org_admin')
    def put(self, org_id):
        '''
        Update an existing organisation.
        '''
        if org_id == '':
            raise handlers.MethodError(
                "Can't use PUT for new organisations (no ID).")

        if self.current_user.role == 'org_admin' \
                and str(self.organisation.id) != org_id:
            raise handlers.AuthzError(
                "You can't modify another organisation's information.")

        try:
            with model.session_scope() as session:
                org = session.query(model.Organisation).get(org_id)
                if org is None:
                    raise ValueError("No such object")
                self._update(org, self.request_son)

                act = Activities(session)
                # is_modified checks nested collections too:
                # http://docs.sqlalchemy.org/en/latest/orm/session_api.html#sqlalchemy.orm.session.Session.is_modified
                if session.is_modified(org):
                    act.record(self.current_user, org, ['update'])
                if not act.has_subscription(self.current_user, org):
                    act.subscribe(self.current_user, org)
                    self.reason("Subscribed to organisation")

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such organisation")
        self.get(org_id)

    def delete(self, org_id):
        if org_id == '':
            raise handlers.MethodError("Organisation ID required")
        try:
            with model.session_scope() as session:
                org = session.query(model.Organisation).get(org_id)
                if org is None:
                    raise ValueError("No such object")

                act = Activities(session)
                act.record(self.current_user, org, ['delete'])

                session.delete(org)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError(
                "Organisation owns content and can not be deleted")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such organisation")

        self.finish()

    def _update(self, org, son):
        '''
        Apply user-provided data to the saved model.
        '''
        update = updater(org)
        update('name', son)
        update('url', son)
        self._save_locations(org, son['locations'])
        self._save_meta(org, son['meta'])

    def _save_locations(self, org, sons):
        column_names = {c.name
                        for c in sqlalchemy.inspect(model.OrgLocation).columns
                        if c.name not in {'id', 'organisation_id'}}

        def loc_eq(a, b):
            return all(a[n] == getattr(b, n) for n in column_names)

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


class PurchasedSurveyHandler(crud.survey.SurveyCentric, handlers.BaseHandler):
    @tornado.web.authenticated
    def head(self, org_id, hierarchy_id):
        self._check_user(org_id)

        with model.session_scope() as session:
            purchased_survey = (session.query(model.PurchasedSurvey)
                .filter_by(survey_id=self.survey_id,
                           hierarchy_id=hierarchy_id,
                           organisation_id=org_id)
                .first())
            if not purchased_survey:
                raise handlers.MissingDocError(
                    "This survey has not been purchased yet")

        self.finish()

    @tornado.web.authenticated
    def get(self, org_id, hierarchy_id):
        if not hierarchy_id:
            self.query(org_id)

        raise handlers.ModelError("Not implemented")

    def query(self, org_id):
        self._check_user(org_id)

        with model.session_scope() as session:
            org = session.query(model.Organisation).get(org_id)
            if not org:
                raise handlers.MissingDocError('No such organisation')

            to_son = ToSon(include=[
                r'/id$',
                r'/title$',
                r'/n_measures$',
                r'/survey/tracking_id$',
                # Descend into list
                r'/[0-9]+$',
                r'/survey$'
            ])
            sons = to_son(org.hierarchies)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('admin')
    def put(self, org_id, hierarchy_id):
        with model.session_scope() as session:
            org = session.query(model.Organisation).get(org_id)
            if not org:
                raise handlers.MissingDocError('No such organisation')
            hierarchy = (session.query(model.Hierarchy)
                .get((hierarchy_id, self.survey_id)))
            if not hierarchy:
                raise handlers.MissingDocError('No such hierarchy')

            purchased_survey = (session.query(model.PurchasedSurvey)
                .get((self.survey_id, hierarchy_id, org.id)))

            if not purchased_survey:
                org.hierarchies.append(hierarchy)

    @handlers.authz('admin')
    def delete(self, org_id, survey_id):
        with model.session_scope() as session:
            org = session.query(model.Organisation).get(org_id)
            if not org:
                raise handlers.MissingDocError('No such organisation')
            hierarchy = (session.query(model.Hierarchy)
                .get((hierarchy_id, self.survey_id)))
            if not hierarchy:
                raise handlers.MissingDocError('No such hierarchy')

            org.surveys.remove(hierarchy)

    def _check_user(self, org_id):
        if org_id != str(self.current_user.organisation_id):
            if not self.has_privillege('consultant'):
                raise handlers.AuthzError(
                    "You can't access another organisation's surveys")


class LocationSearchHandler(handlers.BaseHandler):
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
