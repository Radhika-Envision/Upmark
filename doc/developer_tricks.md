## Database

Connecting to a development database, where the application was started
using `docker-compose`, and thus the database is in a local Docker container:

```bash
sudo docker exec -it aquamark_postgres_1 psql -U postgres
```

Creating a backup of a development database:

```bash
mkdir ~/tmp
sudo docker run -it --rm \
    -v ~/tmp:/backup \
    --link aquamark_postgres_1:postgres \
    postgres:9.4 \
    bash -c "pg_dumpall -U postgres -h postgres > /backup/aq_dump.sql"
```

Restoring a backup:

```bash
mkdir ~/tmp
sudo docker run -it --rm \
    -v ~/tmp:/backup \
    --link aquamark_postgres_1:postgres \
    postgres:9.4 \
    bash -c "psql -U postgres -h postgres < /backup/aq_dump.sql"
```
