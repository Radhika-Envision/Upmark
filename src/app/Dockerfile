FROM ubuntu:16.04

MAINTAINER Wsaa Envision <wsaa@envisionit.com.au>

RUN DEBIAN_FRONTEND=noninteractive \
    apt-get update && \
    apt-get install -y \
        locales \
        --no-install-recommends && \
    locale-gen en_AU.UTF-8 && \
    rm -rf /var/lib/apt/lists/*

ENV LANG en_AU.UTF-8
ENV LANGUAGE en_AU.en
ENV LC_ALL en_AU.UTF-8

# build-essentials is required for building many pip packages
# Git is required by Bower
# cairo2, ffi, jpeg and lxml are required by cariosvg
RUN DEBIAN_FRONTEND=noninteractive \
    apt-get update && \
    apt-get install -y \
        build-essential \
        git \
        libcairo2 \
        libffi-dev \
        libjpeg-dev \
        nodejs \
        npm \
        python3 \
        python3-dev \
        python3-lxml \
        python3-pip \
        python3-psycopg2 \
        --no-install-recommends && \
    which node || apt-get install -y nodejs-legacy && \
    npm install -g bower && \
    pip3 install -vU setuptools pip && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies before copying full source directory. This speeds up
# Docker rebuilds.
COPY requirements.txt requirements_force.txt /tmp/
WORKDIR /tmp
RUN pip3 install --upgrade --force-reinstall -r requirements_force.txt
RUN pip3 install -r requirements.txt

COPY bower.json /tmp/
RUN bower \
        --allow-root \
        --config.interactive=false \
        --config.directory=bower_components \
        --force-latest \
        install

# Copy application to container. For development, mount a volume over this
# directory.
COPY ./ /usr/share/aquamark/app/
WORKDIR /usr/share/aquamark/app/
RUN mv /tmp/bower_components /usr/share/aquamark/.bower_components

ENV PORT=80 \
    DEV_MODE=False \
    PGHOST=postgres \
    PGPORT=5432 \
    PGUSER=postgres \
    PGDATABASE=postgres \
    PGPASSWORD=postgres \
    ANALYTICS_ID= \
    AWS_REGION_NAME=ap-southeast-2 \
    AWS_BUCKET=aquamark \
    AWS_ACCESS_KEY_ID= \
    AWS_SECRET_ACCESS_KEY= \
    PYTHONPATH=.:/usr/share/aquamark/app/server/

EXPOSE 80

CMD ["python3", "./server/app.py"]
