This is the Aquamark application - a web-based survey tool for assessing
water management utilities.

![Aquamark Logo](doc/aquamark_logo.png)

## Deployment

Build with:

```bash
sudo docker build -t vpac/aquamark src/app
```

Run with:

```bash
sudo docker run -d --name postgres_aq postgres:9
sudo docker run -d --name aquamark \
    --link postgres_aq:postgres \
    -e ANALYTICS_ID=foo \
    vpac/aquamark
```

Where `ANALYTICS_ID` is a [Google Analytics][ga] ID. Omit that option to disable
analytics.

The first time the server is started, a default user is created:

 * Email: admin
 * Password: admin

The first thing you should do is log in as that user and change the password.
You might also want to change other details about the default user and
organisation.

[ga]: http://www.google.com.au/analytics/


## Development

The easiest way to run during development is to start a Docker container as
shown above, but mount your code as a volume. Changes you make to the code will
automatically apply to the running container. This way you don't need to worry
about creating a database. Also, expose the web server's port - then you can
just connect to http://localhost:8000 for testing.

```bash
sudo docker run -d --name postgres_aq postgres:9
sudo docker run --rm --name aq \
    --link postgres_aq:postgres \
    -v "$PWD/src/app:/usr/share/aquamark/app" \
    -p 8000:8000 \
    -e DEV_MODE=True \
    -e DEBUG_MODE=True \
    vpac/aquamark
```


## Admin Tool

Some tasks can be performed from the command line using `admin.py`. For example,
to create a new organisation:

```bash
sudo docker run -it --rm --link postgres_aq:postgres vpac/aquamark \
    app/server/admin.py org 'ACME Water' \
        --region=Melbourne \
        --url='http://acme-water.com.au' \
        --customers=2000
```

To create a new user:

```bash
sudo docker run -it --rm --link postgres_aq:postgres vpac/aquamark \
    app/server/admin.py user sue@acme-water.com.au \
        --name='Sue Green' \
        --role=clerk \
        --org='ACME Water'
```

Run `admin.py -h` for more options.


## Dependencies

Client-side scripts are managed with Bower, which will automatically download
them when the application stats (see `start.sh`). When running in release
mode, the application will automatically use CDNs for some scripts and CSS
files, and will minify the others. If you add a dependency or change its
version number, you **must** make sure the versions specified in `bower.json`
and in `server/handlers.py` are the same.
