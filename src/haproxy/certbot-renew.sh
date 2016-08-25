#!/bin/bash

service haproxy reload

/usr/local/bin/certbot-auto renew \
    --standalone \
    --standalone-supported-challenges http-01 \
    --http-01-port 54321 \
    --quiet \
    --no-self-upgrade

mkdir -p /etc/haproxy/certs

for d in $(ls /etc/letsencrypt/live); do
    cat \
        "/etc/letsencrypt/live/${d}/fullchain.pem" \
        "/etc/letsencrypt/live/${d}/privkey.pem" \
        > "/etc/haproxy/certs/${d}.pem"
done

service haproxy reload
