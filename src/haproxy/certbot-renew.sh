#!/bin/bash

logger -p user.notice -t certbot "Attempting renewal"

# certbot-auto uses pip to build stuff, which can cause the machine to run out
# of memory. So enable a swap file first - but disable afterwards, since it
# can hurt the SSD hard drive.
trap 'swapoff /certbot-swapfile' EXIT
if [ ! -e /certbot-swapfile ]; then
    logger -p user.notice -t certbot "Creating swap space"
    fallocate -l 2G /certbot-swapfile
    chmod 600 /certbot-swapfile
    mkswap /certbot-swapfile
fi
swapon /certbot-swapfile

/usr/local/bin/certbot-auto renew \
    --standalone \
    --preferred-challenges http-01 \
    --http-01-port 54321 \
    --quiet \
    --no-self-upgrade \
    --no-bootstrap

if [ $? -ne 0 ]; then
    logger -p user.err -t certbot \
        "Certbot failed. Run again manually to see error."
    exit 1
fi

mkdir -p /etc/haproxy/certs

for d in $(ls /etc/letsencrypt/live); do
    cat \
        "/etc/letsencrypt/live/${d}/fullchain.pem" \
        "/etc/letsencrypt/live/${d}/privkey.pem" \
        > "/etc/haproxy/certs/${d}.pem"
done

service haproxy reload
