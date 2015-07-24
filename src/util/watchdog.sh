#!/usr/bin/env bash

projdir=$(dirname $0)

function error() {
    echo "$@" >&2
}


function install_deps() {

    sudo apt-get update && sudo apt-get install -y python3-pip 
    sudo pip3 install -vU pyyaml docker-py python-dateutil
    if [ $? -ne 0 ]; then
        error "Failed to install Python dependencies."
        exit 1
    fi

}

function cron_job() {

    echo "* * * * * python3 ${projdir}/watchdog.py" > ${projdir}/watchdog
    crontab ${projdir}/watchdog

}

install_deps
cron_job
