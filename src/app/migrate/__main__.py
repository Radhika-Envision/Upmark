from sqlalchemy import func

import model

from .connection import connect_db, scope


connect_db()


class Remapper:

    def __init__(self, rw_staging, ro_upstream):
        self.rw_staging = rw_staging
        self.ro_upstream = ro_upstream

    def get_duplicate_users(self):
        duplicates = []
        users_s = self.rw_staging.query(model.AppUser).all()
        for user_s in users_s:
            user_ro = (
                self.ro_upstream.query(model.AppUser)
                .filter(
                    (func.lower(model.AppUser.name) ==
                     func.lower(user_s.name)) |
                    (func.lower(model.AppUser.email) ==
                     func.lower(user_s.email)))
                .first())
            if user_ro:
                duplicates.append((user_s, user_ro))
        return duplicates

    def get_duplicate_orgs(self):
        duplicates = []
        orgs_s = self.rw_staging.query(model.Organisation).all()
        for org_s in orgs_s:
            org_ro = (
                self.ro_upstream.query(model.Organisation)
                .filter(
                    (func.lower(model.Organisation.name) ==
                     func.lower(org_s.name)))
                .first())
            if org_ro:
                duplicates.append((org_s, org_ro))
        return duplicates

    def remap_users(self):
        duplicates = self.get_duplicate_users()
        for user_s, user_ro in duplicates:
            print("Duplicate user %s: %s -> %s" % (
                user_s.name, user_s.id, user_ro.id))

    def remap_orgs(self):
        duplicates = self.get_duplicate_orgs()
        for org_s, org_ro in duplicates:
            print("Duplicate organisation %s: %s -> %s" % (
                org_s.name, org_s.id, org_ro.id))


with scope('rw_staging') as rw_staging, scope('ro_upstream') as ro_upstream:
    remapper = Remapper(rw_staging, ro_upstream)
    remapper.remap_users()
    remapper.remap_orgs()
