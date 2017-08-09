from sqlalchemy import func
from tqdm import tqdm

import model

from .connection import scope


class Remapper:

    TABLES = [
        model.SurveyGroup.__table__,
        model.Organisation.__table__,
        model.OrgLocation.__table__,
        model.OrgMeta.__table__,
        model.AppUser.__table__,

        model.CustomQuery.__table__,
        model.CustomQuery.__history_mapper__.local_table,

        model.Program.__table__,
        model.Survey.__table__,
        model.QuestionNode.__table__,
        model.ResponseType.__table__,
        model.Measure.__table__,
        model.QnodeMeasure.__table__,
        model.MeasureVariable.__table__,

        model.PurchasedSurvey.__table__,

        model.Submission.__table__,
        model.ResponseNode.__table__,
        model.Response.__table__,
        model.Response.__history_mapper__.local_table,
        model.Attachment.__table__,

        model.Activity.__table__,
        model.Subscription.__table__,

        model.IdMap.__table__,

        model.organisation_surveygroup,
        model.program_surveygroup,
        model.activity_surveygroup,
        model.user_surveygroup,
    ]

    def __init__(self, rw_staging, ro_upstream):
        self.rw_staging = rw_staging
        self.ro_upstream = ro_upstream
        self.dup_ids = set()

    def run(self):
        self.remap_users_and_orgs()
        self.transfer()
        self.rw_staging.rollback()
        self.ro_upstream.commit()

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

    USER_CONSTRAINTS = [
        (
            'activity', 'appuser',
            'activity_subject_id_fkey',
            ['subject_id'], ['id']),
        (
            'custom_query', 'appuser',
            'custom_query_user_id_fkey',
            ['user_id'], ['id']),
        (
            'custom_query_history', 'appuser',
            'custom_query_history_user_id_fkey',
            ['user_id'], ['id']),
        (
            'response', 'appuser',
            'response_user_id_fkey',
            ['user_id'], ['id']),
        (
            'response_history', 'appuser',
            'response_history_user_id_fkey',
            ['user_id'], ['id']),
        (
            'subscription', 'appuser',
            'subscription_user_id_fkey',
            ['user_id'], ['id']),
        (
            'user_surveygroup', 'appuser',
            'user_surveygroup_user_id_fkey',
            ['user_id'], ['id']),
    ]

    ORG_CONSTRAINTS = [
        (
            'appuser', 'organisation',
            'appuser_organisation_id_fkey',
            ['organisation_id'], ['id']),
        (
            'attachment', 'organisation',
            'fk_attachment_organisation',
            ['organisation_id'], ['id']),
        (
            'org_location', 'organisation',
            'org_location_organisation_id_fkey',
            ['organisation_id'], ['id']),
        (
            'org_meta', 'organisation',
            'org_meta_organisation_id_fkey',
            ['organisation_id'], ['id']),
        (
            'organisation_surveygroup', 'organisation',
            'organisation_surveygroup_organisation_id_fkey',
            ['organisation_id'], ['id']),
        (
            'purchased_survey', 'organisation',
            'purchased_survey_organisation_id_fkey',
            ['organisation_id'], ['id']),
        (
            'submission', 'organisation',
            'submission_organisation_id_fkey',
            ['organisation_id'], ['id']),
    ]

    DEFUNCT_CONSTRAINTS = [
        (
            'response', 'appuser',
            'response_user_id_fkey1'),
        (
            'submission', 'organisation',
            'assessment_organisation_id_fkey1'),
    ]

    OTHER_CONSTRAINTS = [
        (
            'qnode', 'qnode',
            'qnode_parent_id_fkey',
            ['parent_id', 'program_id'], ['id', 'program_id']),
    ]

    def drop_constraints(self, session, constraints, if_exists=False):
        if if_exists:
            if_exists_clause = 'IF EXISTS'
        else:
            if_exists_clause = ''

        for constraint in constraints:
            alter_statment = """
                ALTER TABLE {}
                DROP CONSTRAINT {} {}
            """.format(
                constraint[0], if_exists_clause, constraint[2])

            print("Dropping constraint %s" % constraint[2])
            session.execute(alter_statment)

    def create_constraints(self, session, constraints):
        for constraint in constraints:
            alter_statment = """
                ALTER TABLE {}
                ADD CONSTRAINT {}
                FOREIGN KEY ({})
                REFERENCES {} ({});
            """.format(
                constraint[0], constraint[2],
                ', '.join(constraint[3]), constraint[1],
                ', '.join(constraint[4]))

            print("Creating constraint %s" % constraint[2])
            session.execute(alter_statment)

    def remap_users(self):
        duplicates = self.get_duplicate_users()
        for user_s, user_ro in duplicates:
            print("Duplicate user %s: %s -> %s" % (
                user_s.name, user_s.id, user_ro.id))
            self.rw_staging.execute(
                model.Activity.__table__.update()
                .where(model.Activity.subject_id == user_s.id)
                .values({'subject_id': user_ro.id}))
            self.rw_staging.execute(
                model.CustomQuery.__history_mapper__.local_table.update()
                .where(model.CustomQueryHistory.user_id == user_s.id)
                .values({'user_id': user_ro.id}))
            self.rw_staging.execute(
                model.CustomQuery.__table__.update()
                .where(model.CustomQueryHistory.user_id == user_s.id)
                .values({'user_id': user_ro.id}))
            self.rw_staging.execute(
                model.Response.__history_mapper__.local_table.update()
                .where(model.ResponseHistory.user_id == user_s.id)
                .values({'user_id': user_ro.id}))
            self.rw_staging.execute(
                model.Response.__table__.update()
                .where(model.Response.user_id == user_s.id)
                .values({'user_id': user_ro.id}))
            self.rw_staging.execute(
                model.Subscription.__table__.update()
                .where(model.Subscription.user_id == user_s.id)
                .values({'user_id': user_ro.id}))
            self.rw_staging.execute(
                model.user_surveygroup.update()
                .where(model.user_surveygroup.c.user_id == user_s.id)
                .values({'user_id': user_ro.id}))

            self.rw_staging.execute("""
                UPDATE activity
                SET ob_refs=array_replace(ob_refs, '{old}', '{new}'),
                    ob_ids=array_replace(ob_ids, '{old}', '{new}')
                WHERE ARRAY['{old}'::uuid] <@ ob_refs
                   OR ARRAY['{old}'::uuid] <@ ob_ids;
            """.format(old=user_s.id, new=user_ro.id))
            self.rw_staging.execute("""
                UPDATE subscription
                SET ob_refs=array_replace(ob_refs, '{old}', '{new}')
                WHERE ARRAY['{old}'::uuid] <@ ob_refs;
            """.format(old=user_s.id, new=user_ro.id))

            self.rw_staging.add(model.IdMap(
                old_id=user_s.id, new_id=user_ro.id))
            user_s.id = user_ro.id
            self.dup_ids.add(user_ro.id)

        self.rw_staging.flush()

    def remap_orgs(self):
        duplicates = self.get_duplicate_orgs()
        for org_s, org_ro in duplicates:
            print("Duplicate organisation %s: %s -> %s" % (
                org_s.name, org_s.id, org_ro.id))
            self.rw_staging.execute(
                model.AppUser.__table__.update()
                .where(model.AppUser.organisation_id == org_s.id)
                .values({'organisation_id': org_ro.id}))
            self.rw_staging.execute(
                model.Submission.__table__.update()
                .where(model.Submission.organisation_id == org_s.id)
                .values({'organisation_id': org_ro.id}))
            self.rw_staging.execute(
                model.Attachment.__table__.update()
                .where(model.Attachment.organisation_id == org_s.id)
                .values({'organisation_id': org_ro.id}))
            self.rw_staging.execute(
                model.OrgLocation.__table__.update()
                .where(model.OrgLocation.organisation_id == org_s.id)
                .values({'organisation_id': org_ro.id}))
            self.rw_staging.execute(
                model.OrgMeta.__table__.update()
                .where(model.OrgMeta.organisation_id == org_s.id)
                .values({'organisation_id': org_ro.id}))
            self.rw_staging.execute(
                model.organisation_surveygroup.update()
                .where(model.organisation_surveygroup.c.organisation_id ==
                       org_s.id)
                .values({'organisation_id': org_ro.id}))
            self.rw_staging.execute(
                model.PurchasedSurvey.__table__.update()
                .where(model.PurchasedSurvey.organisation_id == org_s.id)
                .values({'organisation_id': org_ro.id}))
            self.rw_staging.execute(
                model.Submission.__table__.update()
                .where(model.Submission.organisation_id == org_s.id)
                .values({'organisation_id': org_ro.id}))

            self.rw_staging.execute("""
                UPDATE activity
                SET ob_refs=array_replace(ob_refs, '{old}', '{new}'),
                    ob_ids=array_replace(ob_ids, '{old}', '{new}')
                WHERE ARRAY['{old}'::uuid] <@ ob_refs
                   OR ARRAY['{old}'::uuid] <@ ob_ids;
            """.format(old=org_s.id, new=org_ro.id))
            self.rw_staging.execute("""
                UPDATE subscription
                SET ob_refs=array_replace(ob_refs, '{old}', '{new}')
                WHERE ARRAY['{old}'::uuid] <@ ob_refs;
            """.format(old=org_s.id, new=org_ro.id))

            self.rw_staging.add(model.IdMap(
                old_id=org_s.id, new_id=org_ro.id))
            org_s.id = org_ro.id
            self.dup_ids.add(org_ro.id)

        self.rw_staging.flush()

    def remap_users_and_orgs(self):
        self.drop_constraints(self.rw_staging, self.USER_CONSTRAINTS)
        self.drop_constraints(self.rw_staging, self.DEFUNCT_CONSTRAINTS, True)
        self.drop_constraints(self.rw_staging, self.ORG_CONSTRAINTS)
        self.remap_users()
        self.remap_orgs()
        self.create_constraints(self.rw_staging, self.ORG_CONSTRAINTS)
        self.create_constraints(self.rw_staging, self.USER_CONSTRAINTS)
        self.rw_staging.flush()

    def transfer(self):
        self.drop_constraints(self.ro_upstream, self.OTHER_CONSTRAINTS)

        for table in tqdm(self.TABLES):
            query = self.rw_staging.query(table)

            if self.dup_ids:
                if str(table) in {'appuser', 'organisation'}:
                    query = query.filter(~table.c.id.in_(self.dup_ids))
                elif str(table) == 'subscription':
                    query = (
                        query
                        .filter(~table.c.user_id.in_(self.dup_ids))
                        .filter(~table.c.ob_refs.overlap(self.dup_ids)))

            count = query.count()
            rows = query.all()

            tqdm.write("Transferring %s" % table)

            for row in tqdm(rows, total=count):
                self.ro_upstream.execute(
                    table.insert()
                    .values(row))

        print()
        self.create_constraints(self.ro_upstream, self.OTHER_CONSTRAINTS)


def remap():
    with scope('rw_staging') as rw_staging, \
            scope('ro_upstream') as ro_upstream:
        remapper = Remapper(rw_staging, ro_upstream)
        remapper.run()
