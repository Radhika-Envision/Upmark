These scripts assist in the merging of two Upmark databases. The scripts
operate on a source and target database:

- `source`: The database to copy _from_
- `target`: The database to copy _to_

## Preparation

Take a backup of your source database using `pg_dump`. The name of the source
backup
file is important: it should be `source-old.psql`. However the `source` part
of the name can be whatever you like; it will be specified as an argument to
the script.

```
pg_dump --format custom --blobs --file source-old.psql
```

The target database should be initially empty. The script will create it for
you.


## Running

Best practice is to start with an empty _offline_ target database and merge
multiple source databases into it, one after another.

The tool operates on docker containers using docker-compose. The database
containers will be:

- `source_postgres_1`
- `target_postgres_1`

Where `source` and `target` are names that you have provided to the script.

**Important**: The target database will be modified. The source database will
be **destroyed** to allow a clean import of `source-old.psql`. Both databases
will be upgraded to the latest version of the database schema. Do not use this
tool on a live system.

```
cd <PROJECT ROOT>
./src/app/migrate/migrate.sh <SOURCE NAME> <TARGET NAME>
```
