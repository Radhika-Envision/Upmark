FROM ubuntu:14.04

MAINTAINER Alex Fraser <alex@vpac-innovations.com.au>

RUN DEBIAN_FRONTEND=noninteractive \
    apt-get update && \
    apt-get install -y \
        python3 \
        python3.4-dev \
        python3-pip \
        --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Setuptools needs to be installed to keep up with the changing requirements
# of pip packages.
# setuptools 20.2.2 is broken; fails to parse requirements for boto->futures:
# https://bitbucket.org/pypa/setuptools/issues/502/packaging-164-does-not-allow-whitepace
# when this is fixed, remove the version qualifier
RUN pip3 install -vU 'setuptools<20.2.2'
RUN pip3 install -vU boto3 awscli

COPY ./ /usr/share/aquamark/database
WORKDIR /usr/share/aquamark/database

ENV AWS_RDS_IDENTIFIER=aquamark \
    AWS_REGION_NAME=ap-southeast-2 \
    AWS_ACCESS_KEY_ID= \
    AWS_SECRET_ACCESS_KEY= \
    BACKUP_CRON_INTERVAL=300

CMD ["python3", "./backup.py"]
