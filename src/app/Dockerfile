FROM ubuntu:14.04

MAINTAINER Alex Fraser <alex@vpac-innovations.com.au>

RUN DEBIAN_FRONTEND=noninteractive \
    apt-get update && \
    apt-get install -y \
        npm \
        nodejs \
        build-essential \
        python3 \
        python3.4-dev \
        virtualenvwrapper \
        python3-pip \
        python3-psycopg2 \
        git \
        --no-install-recommends && \
    which node || sudo apt-get install -y nodejs-legacy && \
    npm install -g bower && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install -vU setuptools

# Install dependencies before copying full source directory. This speeds up
# Docker rebuilds.
COPY requirements.txt bower.json /tmp/
WORKDIR /tmp
RUN pip3 install -r requirements.txt
RUN bower \
        --allow-root \
        --config.interactive=false \
        --config.directory=bower_components \
        --force-latest \
        install

# Copy application to container. For development, mount a volume over this
# directory.
COPY ./ /usr/share/aquamark/app/
WORKDIR /usr/share/aquamark
RUN mv /tmp/bower_components /usr/share/aquamark/.bower_components

ENV PORT=8000 \
    DEV_MODE=False \
    DATABASE_URL=postgresql://postgres:postgres@postgres/postgres \
    ANALYTICS_ID=

EXPOSE 8000

CMD ["python3", "./app/server/app.py"]
