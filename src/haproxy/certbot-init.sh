#!/bin/bash

if [ ! -e /usr/local/bin/certbot-auto ]; then
    wget https://dl.eff.org/certbot-auto -O /usr/local/bin/certbot-auto
    chmod a+x /usr/local/bin/certbot-auto
fi

CB_CHALLENGE="--standalone \
    --standalone-supported-challenges http-01 \
    --http-01-port 54321"

if ! find /etc/haproxy/certs -mindepth 1 -print -quit | grep -q .; then
    # Certs directory is empty; use alternate config file
    echo "Using alternative haproxy file (no certs yet)"
    service haproxy stop
    haproxy -D -f haproxy-bootstrap.cfg
    sleep 2
    if ! ps ax | grep haproxy | grep -v grep; then
        echo "Failed to start haproxy"
        exit 1
    fi
fi

/usr/local/bin/certbot-auto certonly $CB_CHALLENGE

if ! service haproxy status; then
    # Kill the temporary server
    killall haproxy
fi
