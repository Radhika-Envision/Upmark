from sqlalchemy.orm import aliased, object_session

import model


def filter_surveygroups(session, query, user_id, mappers, relationship_tables):
    '''
    Modify a query to only return entities that share at least one survey group
    with a given user.

    @param query: A query for some entity type
    @param user_id: The user's ID
    @param mappers: A collection of mappers that link the entity being queried
        to an entity that has survey groups. For example, a qnode has no survey
        groups but its program does, so model.Program should be in this list.
    @param relationship_tables: A collection of many-to-many mapping tables,
        each of which links at least one of the mappers to survey groups. For
        example, model.organisation_surveygroup.
    @return A derived query.
    '''
    for mapper in mappers:
        if mapper not in [m.class_ for m in query._join_entities]:
            query = query.join(mapper)

    relationship_tables = [aliased(mapper) for mapper in relationship_tables]
    for table in relationship_tables:
        table = aliased(table)
        query = query.join(table)
        query = query.filter(
            table.columns.surveygroup_id.in_(
                session.query(model.user_surveygroup.columns.surveygroup_id)
                .filter(model.user_surveygroup.columns.user_id == user_id)))

    return query


def assign_surveygroups(user_session, target_entity, source_entity):
    '''
    Assigns `source_entity.surveygroups` to `target_entity.surveygroups`.
    `target_entity` must be a real database entity.
    `source_entity` may be a real entity or not. The actual groups will be
    fetched from the database.

    Returns True iff `target_entity`'s groups are materially changed.

    May raise an authorisation exception according to the
    `surveygroup_delegate` rule.

    Raises `ValueError` if one of the new surveygroups can't be found.
    '''
    old_ids = {str(sg.id) for sg in target_entity.surveygroups if sg}
    new_ids = {str(sg.id) for sg in source_entity.surveygroups if sg}
    if old_ids == new_ids:
        return False

    session = object_session(user_session.user)
    new_surveygroups = set(
        session.query(model.SurveyGroup)
        .filter(model.SurveyGroup.id.in_(new_ids))
        .all())
    if len(new_surveygroups) != len(new_ids):
        raise ValueError("Specified survey group not found")

    changed_surveygroups = target_entity.surveygroups.symmetric_difference(
        new_surveygroups)

    policy = user_session.policy.derive({
        'surveygroups': changed_surveygroups,
    })
    policy.verify('surveygroup_delegate')

    target_entity.surveygroups = new_surveygroups

    return True
