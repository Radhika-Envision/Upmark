#!/usr/bin/env bash

projdir=$(readlink -f $(dirname $0))

function error() {
    echo "$@" >&2
}

function cron_job() {

    echo "* * * * * python3 ${projdir}/watchdog.py" > ${projdir}/watchdog
    crontab ${projdir}/watchdog

}

cron_job
