This document describes how to use [cURL][curl] to access Aquamark web services.

First, set some variables for the Aquamark server. These will be reused in all cURL commands:

```bash
AQ_HOST=http://localhost:8000
AQ_OPTS="-b .cookies.txt --cookie _xsrf=foo -H X-Xsrftoken:foo"
```

Then authenticate. The second line shows the status of the login (should be `/`):

```bash
curl $AQ_OPTS -c .cookies.txt -F email=admin -F password=admin "$AQ_HOST/login" \
    -v 2>&1 | grep Location:
```

Now other services can be accessed, as long as `$AQ_OPTS` is included in the `curl` command. For example, to get a list of users:

```bash
curl $AQ_OPTS $AQ_HOST/user.json
```

## Using a Non-Public Docker Container

If you have not bound to a public port (using `docker run -p ...`), then you can still access the web services via the container's IP address. In that case, set `AQ_HOST` like this:

```bash
AQ_IP=$(sudo docker inspect -f {{.NetworkSettings.IPAddress}} aq)
AQ_HOST=http://${AQ_IP}:8000
```

[curl]: https://en.wikipedia.org/wiki/CURL#curl
