# Let's Encrypt

You can use [Let's Encrypt] to provde the SSL certificates.

 1. Make sure the domain name is propery set up, or this will not work.

 1. Install the [Let's Encrypt client].

    ```bash
    cd
    git clone https://github.com/letsencrypt/letsencrypt
    ```

 1. Run Let's Encrypt to get a certificate. First make sure port 80 and 443 are
    available: stop other web servers, and ensure your firewall/security group
    allows it. Then run:

    ```bash
    cd ~/letsencrypt
    ./letsencrypt-auto certonly --standalone -d aquamark.vpac-innovations.com.au
    ```

    Enter your email address, and read the terms and conditions when promted. It
    should say something like:

    > Congratulations! Your certificate and chain have been saved at
      `/etc/letsencrypt/live/aquamark.vpac-innovations.com.au/fullchain.pem`.
      Your cert will expire on 2016-04-27. To obtain a new version of the
      certificate in the future, simply run Let's Encrypt again.

 1. Start the Docker containers __\*__:

    ```bash
    cd ~/aquamark
    sudo docker-compose build webletsencrypt
    sudo docker-compose up -d webletsencrypt
    ```

[Let's Encrypt]: https://letsencrypt.org/
[Let's Encrypt client]: https://letsencrypt.readthedocs.org/en/latest/using.html#installation
