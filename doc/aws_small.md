These instructions are for setting up an instance of Upmark on Amazon, with a
self-hosted database (no RDS or S3).

 1. Start up an Ubuntu machine on AWS. A `t2.micro` instance should do.

 1. Point a domain name at it.

 1. Install dependencies. Haproxy 1.6 is required for certain SSL options.

    ```
    sudo add-apt-repository ppa:vbernat/haproxy-1.6
    sudo apt-get update
    sudo apt-get install \
        git \
        haproxy \
        make
    ```

 1. [Install Docker].

 1. [Install docker-compose].

 1. Get the app source.

    1. Generate a key.

        ```
        ssh-keygen
        cat ~/.ssh/id_rsa.pub
        ```

    1. [Install it on GitHub][deploy-key].

    1. Fetch the source.

        ```
        git clone git@github.com:vpac-innovations/aquamark.git
        ```

 1. Configure the app.

    ```
    cp -a src/app/config ../aq_conf
    nano ../aq_conf/aq.conf
    nano ../aq_conf/recalculate.yaml
    nano ../aq_conf/notification.yaml
    ```

 1. Build and run the app.

    ```
    make version
    sudo docker-compose run --rm web alembic upgrade head
    sudo docker-compose up -d web recalc notify
    ```

 1. Configure haproxy. Get the IP address of the `web` container and put it in
    the haproxy config file.

    ```
    sudo docker-compose logs web | grep 'Bound to:'
    sudo cp src/haproxy/haproxy.cfg /etc/haproxy
    sudo nano /etc/haproxy/haproxy.cfg
    ```

 1. Get a certificate using Let's Encrypt. It will ask you which domains you
    want to get certificates for. Also install a cron job that will attempt to
    refresh the certificates every day\*.

    ```
    cd src/haproxy
    ./certbot-init.sh
    ./certbot-renew.sh
    sudo crontab -l | { cat; echo "50 3 * * * $PWD/certbot-renew.sh"; } | sudo crontab -
    ```

    If you prefer not to use Let's Encrypt, just put the certificate chain
    in `/etc/haproxy/certs` and restart haproxy.

\* A high refresh frequency is recommended in case the cerficiate is revoked
before it would naturally expire.


[Install Docker]: https://docs.docker.com/engine/installation/linux/ubuntulinux/
[Install docker-compose]: https://docs.docker.com/compose/install/
[deploy-key]: https://developer.github.com/guides/managing-deploy-keys/#deploy-keys
