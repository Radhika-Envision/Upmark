#!/usr/bin/env bash

projdir=$(readlink -f $(dirname $0))

function error() {
    echo "$@" >&2
}


function install_deps() {

    which pip3 || sudo apt-get update && sudo apt-get install -y python3-pip
    sudo pip3 install -vU setuptools
    sudo pip3 install -r ${projdir}/requirements.txt
    if [ $? -ne 0 ]; then
        error "Failed to install Python dependencies."
        exit 1
    fi

}

cron_job
