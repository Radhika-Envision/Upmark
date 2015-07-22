#!/usr/bin/env bash

projdir=$(dirname $0)
app=${projdir}/server/app.py


function error() {
    echo "$@" >&2
}


function install_deps() {

    sudo apt-get update && apt-get install -y python3-pip
    pip3 install -vU boto3 awscli
    pip3 install -r ${projdir}/requirements.txt
    if [ $? -ne 0 ]; then
        error "Failed to install Python dependencies."
        exit 1
    fi


}

function cron_job() {
    crontab ${projdir}/cron_backup
}

install_deps
cron_job
