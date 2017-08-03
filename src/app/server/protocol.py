import logging

import tornado.web

import base_handler
import model


log = logging.getLogger('app.protocol')


class PingHandler(base_handler.BaseHandler):
    '''
    Handler for load balancer health checks. For configuring AWS ELB, see:
    https://docs.aws.amazon.com/ElasticLoadBalancing/latest/DeveloperGuide/elb-healthchecks.html
    '''

    def get(self):
        # Check that the connection to the database works
        with model.session_scope() as session:
            session.query(model.SystemConfig).count()

        self.set_header("Content-Type", "text/plain")
        self.write("Web services are UP")
        self.finish()


class RedirectHandler(base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self):
        url = self.get_argument("url", "/")
        log.info("url: %s", url)
        self.redirect(url)
