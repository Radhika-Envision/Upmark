# Database Administration

## Taking manual backups from RDS

If you are using [AWS RDS][aws] for your database, you can usually use its
automated backup facility. In that case, you can ignore the following
instructions.

Fire up a `postgres` container into a bash shell. Set some environment
variables so you can connect to the RDS instance.

```
mkdir -p backup
sudo docker run --rm -it -v $PWD/backup:/backup postgres:9 bash
```

In the container:

```
export PGHOST=<host>
export PGUSER=postgres
export PGDATABASE=postgres
export PGPASSWORD=<password>

TODAY=$(date '+%F')
pg_dump --format custom --blobs --file "upmark_dump-${TODAY}.psql"
exit
```

The backup should now be in the `backup` directory.

## Docker-managed PostgreSQL

These instructions are for working with backups for your Docker-based Postgres
database.

To work with the local database, use the `dbadmin` service. The `../backup`
directory gets mapped as a volume, and is used as the default working directory.

To open a `psql` shell:

```
mkdir -p ../backup
sudo docker-compose run --rm dbadmin
```

To make a backup for today:

```
TODAY=$(date '+%F')
mkdir -p ../backup
sudo docker-compose run --rm dbadmin \
    pg_dump --format custom --blobs --file "local_dump-${TODAY}.psql"
```

To restore a backup from today (be very careful when running these commands
on the production database):

```
sudo docker-compose run --rm dbadmin bash -c "
    dropdb postgres ;
    createdb postgres &&
    pg_restore -d postgres 'local_dump-${TODAY}.psql'"
```


[aws]: aws.md
