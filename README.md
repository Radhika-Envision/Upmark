This is the Upmark survey platform - a web-based
survey tool for comparing organisations that manage large numbers of assets,
such as water utilities.

For historical reasons, the source code and build instructions may refer to
Upmark's working title, "Aquamark".


## Development

The easiest way to run during development is to use Docker Compose. First copy
the config files to be out of the source tree and initialise the database:

```
cp -r src/app/config ../aq_conf
echo 'DEV_MODE=True' >> ../aq_conf/aq.conf
sudo docker-compose run --rm web alembic upgrade head
```

Now start the `web` service:

```
sudo docker-compose run --rm web
```

> `INFO  [app] Try opening http://172.17.0.5:8000`

Open the URL suggested by the app in your browser. The default username
and password are `admin`/`admin`.

When you run in `DEV_MODE`:

 - The aggressive cache-busting mechanism for most resources is disabled. This
   makes it easier to set breakpoints in your browser's debugger - but it means
   you'll probably need to [disable caching] in your browser.
 - The app will reload every time the source code changes. The `web` service is
   configured to read the source code directly from the host (using Docker
   volumes).
 - Exception tracebacks will be sent to the client in the HTTP response body.

[disable caching]: http://stackoverflow.com/a/7000899/320036


## Deployment

 - [Deploy to a single self-contained machine](doc/aws_small.md). Includes
   instructions for setting up Let's Encrypt.
 - [Deploy to a group of machines with a shared database](doc/aws.md).

See also:

 - [Database Administration][backup]

[backup]: doc/backup.md


## Dependencies

Client-side scripts are managed with Bower, which will automatically download
them when building with Docker. When not running in dev mode (see [aq.conf]),
the application will automatically use CDNs for some scripts and CSS
files, and will minify the others. If you add a dependency or change its
version number, you **must** make sure the versions specified in `bower.json`
and in `server/handlers.py` are the same.


[aq.conf]: src/app/config/aq.conf


## Debugging

You can debug the web server with the intereactive debugger, pudb. To do so,
edit the file you want to debug and import the `pudb` module. Then add a call to
`set_trace` to add a breakpoint. For example:

```diff
class ResponseHistoryHandler(handlers.Paginate, handlers.BaseHandler):
    @tornado.web.authenticated
    def get(self, assessment_id, measure_id):
+       import pudb
+       pudb.set_trace()
        with model.session_scope() as session:
            # Current version
```

Then start the container with an interactive TTY:

```
sudo docker-compose run --rm web
```

If you're not using docker-compose, add the `-it` to your Docker run command.

Next time you make an appropriate web request, the breakpoint will be triggered
and you will have an interactive debugger in your console.
