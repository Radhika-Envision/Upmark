# Database Administration

These instructions are for working with backups for your Docker-based Postgres
database. If you are using [AWS RDS][aws] for your database, you can use its
automated backup facility.

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

To restore a backup from today (be very careful not when running these commands
on the production database):

```
sudo docker-compose run --rm dbadmin bash -c "
    dropdb postgres ;
    createdb postgres &&
    pg_restore -d postgres 'local_dump-${TODAY}.psql'"
```


[aws]: aws.md
