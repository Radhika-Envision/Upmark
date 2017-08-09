from tornado.escape import json_encode
import tornado.web

import base_handler
import model


class IdMapperHandler(base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self):
        '''
        If an entity's ID changes, it will be stored in a mapping table. This
        service looks up how IDs have changed.
        '''

        with model.session_scope() as session:
            mappings = (
                session.query(model.IdMap)
                .filter(model.IdMap.old_id.in_(self.get_arguments('ids')))
                .all())

            son = {
                str(mapping.old_id): str(mapping.new_id)
                for mapping in mappings}

        for old_id in self.get_arguments('ids'):
            if old_id not in son:
                son[old_id] = old_id
        n_changed = sum(k != v for k, v in son.items())

        self.reason("%d IDs have changed" % n_changed)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()
