from sqlalchemy import func

import model

from .connection import connect_db, scope


connect_db()

# with scope('source') as source, scope('target') as target:
#     print(source.query(model.AppUser).count())
#     print(target.query(model.AppUser).count())


def print_user_mapping():
    with scope('rw_staging') as source, scope('ro_upstream') as target:
        users_s = source.query(model.AppUser).all()
        for user_s in users_s:
            user_ro = (
                target.query(model.AppUser)
                .filter(
                    (func.lower(model.AppUser.name) ==
                     func.lower(user_s.name)) |
                    (func.lower(model.AppUser.email) ==
                     func.lower(user_s.email)))
                .first())
            if not user_ro:
                continue
            print("Duplicate user %s: %s -> %s" % (
                user_s.name, user_s.id, user_ro.id))


def print_org_mapping():
    with scope('rw_staging') as source, scope('ro_upstream') as target:
        orgs_s = source.query(model.Organisation).all()
        for org_s in orgs_s:
            org_ro = (
                target.query(model.Organisation)
                .filter(
                    (func.lower(model.Organisation.name) ==
                     func.lower(org_s.name)))
                .first())
            if not org_ro:
                continue
            print("Duplicate organisation %s: %s -> %s" % (
                org_s.name, org_s.id, org_ro.id))


print_user_mapping()
print_org_mapping()
