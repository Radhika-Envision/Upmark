# Database Backups

These instructions are for working with backups for your Docker-based Postgres
database. If you are using [AWS RDS][aws] for your database, you can use its
automated backup facility.

First launch a temporary Postgres container to run the commands in, linking
to the target postgres container:

```bash
DATE=$(date '+%Y-%m-%d')
mkdir -p "backup/$DATE"
sudo docker run --rm -it \
    --link aquamark_postgres_1:postgres \
    -v "$PWD/backup/<DATE>:/backup"
    postgres:9 bash
```

Now in the temporary container, dump the primary database, and restore it
into your staging container (see AWS RDS console for the ENDPOINT value):

```bash
cd /backup
ENDPOINT=postgres:5432
CONN=postgresql://postgres@$ENDPOINT/postgres
pg_dump --format custom --blobs --verbose ${CONN} --file aq_dump
```

The password of the staging database defaults to `postgres`.

You should now have a database dump in the `backup/$DATE` directory.

To restore from backup, start a temporary container as above. Inside it, run:

```bash
cd /backup
# Be very careful not to run these commands against the primary database:
dropdb -h postgres -U postgres postgres
createdb -h postgres -U postgres postgres
pg_restore -h postgres -U postgres -d postgres aq_dump
```

[aws]: aws.md
