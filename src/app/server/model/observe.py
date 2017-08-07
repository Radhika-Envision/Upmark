__all__ = ['ActionDescriptor', 'Observable']

from collections import namedtuple


ActionDescriptor = namedtuple(
    'ActionDescriptor',
    'message, ob_type, ob_ids, ob_refs')


class Observable:
    '''
    Mixin for mappers that can generate :py:class:`Activities <Activity>`.
    '''

    @property
    def ob_title(self):
        '''
        @return human-readable descriptive text for the object (e.g. its name).
        '''
        return self.title

    @property
    def ob_type(self):
        '''
        @return the type of object as a string.
        '''
        raise NotImplementedError()

    @property
    def ob_ids(self):
        '''
        @return a minimal list of IDs that uniquly identify the object, in
        descending order of specificity. E.g. [measure_id, program_id], because
        the measure belongs to the program.
        '''
        raise NotImplementedError()

    @property
    def action_lineage(self):
        '''
        @return a list of IDs that give a detailed path to the object, in order
        of increasing specificity. E.g.
        [program_id, survey_id, survey_id, qnode_id, qnode_id, measure_id]
        '''
        raise NotImplementedError()

    @property
    def action_descriptor(self):
        '''
        @return an ActionDescriptor for the object.
        '''
        return ActionDescriptor(
            self.ob_title,
            self.ob_type,
            self.ob_ids,
            [item.id for item in self.action_lineage])

    @property
    def surveygroups(self):
        '''
        @return a collection of surveygroups that the object belongs to.
        '''
        raise NotImplementedError()
