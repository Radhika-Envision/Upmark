#!/usr/bin/env bash

set -e

OLD_UPMARK=${1?$'Missing source project name'}
NEW_UPMARK=${2?$'Missing target project name'}

if [ ! -f "../backup/${OLD_UPMARK}-old.psql" ]; then
    echo "Missing source database backup ../backup/${OLD_UPMARK}-old.psql"
    exit 1
fi

echo "Ensuring docker images are up to date and running"
sudo docker-compose -p ${OLD_UPMARK} build web
sudo docker-compose -p ${NEW_UPMARK} build web

if sudo docker ps -a | grep -q "${OLD_UPMARK}_postgres_1"; then
    echo "Dropping old database"
    sudo docker rm -fv "${OLD_UPMARK}_postgres_1"
fi

echo "Ensuring databases are running"
sudo docker-compose -p ${OLD_UPMARK} up -d postgres
sudo docker-compose -p ${NEW_UPMARK} up -d postgres
sleep 5

echo "Importing old data"
sudo docker-compose -p ${OLD_UPMARK} run --rm dbadmin \
    psql -c "CREATE USER analyst WITH PASSWORD 'some rubbish'"
sudo docker-compose -p ${OLD_UPMARK} run --rm dbadmin \
    pg_restore -d postgres ${OLD_UPMARK}-old.psql

echo "Upgrading schemas"
sudo docker-compose -p ${OLD_UPMARK} run --rm web alembic upgrade head
sudo docker-compose -p ${NEW_UPMARK} run --rm web alembic upgrade head

echo "Renaming survey group to '${OLD_UPMARK}'"
sudo docker-compose -p ${OLD_UPMARK} run --rm dbadmin \
    psql -c "UPDATE surveygroup SET title='${OLD_UPMARK}'"

echo "Transferring data from ${OLD_UPMARK} to ${NEW_UPMARK}"
old_ip=$(sudo docker inspect ${OLD_UPMARK}_postgres_1 | \
    sed -nE 's/.*IPAddress": "([0-9.]+)".*/\1/p')
new_ip=$(sudo docker inspect ${NEW_UPMARK}_postgres_1 | \
    sed -nE 's/.*IPAddress": "([0-9.]+)".*/\1/p')
sudo docker run --rm -it \
    -e HISTFILE=/root/scratch/bash_history \
    -e XDG_CONFIG_HOME=/root/scratch \
    -e TERM=xterm-color \
    -v $PWD/src/app:/usr/share/aquamark/app \
    -v $PWD/scratch:/root/scratch \
    --network host \
    -e SOURCE=${old_ip} \
    -e TARGET=${new_ip} \
    ${NEW_UPMARK}_web \
    python3 -m migrate
