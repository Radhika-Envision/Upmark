## Web Service Unit Tests

These are unit tests for the web services. To run them, first **create a
separate database**. That is very important, because the tests will destroy the
contents of the database.

```bash
sudo docker run -d --name postgres_aq_test postgres:9
```

Then run the test suite:

```bash
sudo docker run --rm --link postgres_aq_test:postgres \
    -v "$PWD/src/app:/usr/share/aquamark/app" \
    vpac/aquamark \
    app/test-server/run_tests.sh
```
