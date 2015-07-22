#!/usr/bin/env bash

projdir=$(dirname $0)
app=${projdir}/server/app.py


function error() {
    echo "$@" >&2
}


function install_deps() {

    sudo apt-get update && sudo apt-get install -y python3-pip
    sudo pip3 install -vU boto3 awscli
    if [ $? -ne 0 ]; then
        error "Failed to install Python dependencies."
        exit 1
    fi
    aws configure    

}

function cron_job() {
    crontab ${projdir}/cron_backup
}

install_deps
cron_job
