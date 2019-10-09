## Web Service Unit Tests

These are unit tests for the web services. To run them, first **create a
separate database**. This is very important, because the tests will destroy the
contents of the database. The database should be created to use a RAM disk for
storage to speed up the tests and minimise hard drive wear.

```bash
TMPDIR=$(mktemp -d)
sudo mount -t tmpfs -o size=512M tmpfs $TMPDIR
sudo docker run -d --name postgres_aq_test \
    -v "$TMPDIR:/var/lib/postgresql/data" \
    postgres:9
```

Then run the test suite:

```bash
sudo docker run --rm --link postgres_aq_test:postgres \
    -v "$PWD/src/app:/usr/share/aquamark/app" \
    vpac/aquamark \
    app/test-server/run_tests.sh
```
