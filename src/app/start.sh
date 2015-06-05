#!/usr/bin/env bash

VIRTENV=aquamark

projdir=$(dirname $0)
app=${projdir}/server/app.py


function error() {
    echo "$@" >&2
}


function read_config() {
    local secret config
    config=${projdir}/config/config.sh

    if [ ! -e ${config} ]; then
        cp ${config}.SAMPLE ${config}
    fi

    source ${config}
}


function install_deps() {
    local venvloc

    if $(which virtualenvwrapper.sh); then
        error "Using virtualenvwrapper.sh"
        source $(which virtualenvwrapper.sh)
    elif [ -e /etc/bash_completion.d/virtualenvwrapper ]; then
        error "Using /etc/bash_completion.d/virtualenvwrapper"
        source /etc/bash_completion.d/virtualenvwrapper
    else
        error "Failed to find virtualenvwrapper."
        exit 1
    fi

    workon $VIRTENV
    if [ $? -ne 0 ]; then
        error "Failed to switch to virtual environment. But no need to panic; "
        error "attempting to create it now."
        mkvirtualenv --python=$(which python3) $VIRTENV
    fi

    pip3 install -vU setuptools
    pip3 install -r ${projdir}/requirements.txt
    if [ $? -ne 0 ]; then
        error "Failed to install Python dependencies."
        exit 1
    fi

    $SHELL -c "cd ${projdir} && bower --allow-root --config.interactive=false --force-latest install"
    if [ $? -ne 0 ]; then
        error "Failed to install JavaScript dependencies. Is bower properly "
        error " installed? You may need to restart your shell."
        exit 1
    fi
}

read_config
install_deps

if [ "$1" != "install" ]; then
    exec python3 ${app}
fi
