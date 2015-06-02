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

#ENV MONGO_URL mongodb://[username:password@]host1[:port1][,host2[:port2],...[,hostN[:portN]]][/[database][?options]]
ENV MONGO_URL mongodb://mongodb/aquamark

COPY ./ /usr/share/aquamark
COPY config/config.sh.DOCKER_SAMPLE /usr/share/aquamark/config/config.sh
#for the development use docker -v to link your source code to container
#refer to aquamark wiki

WORKDIR /usr/share/aquamark

ENV PORT=80 DEV_MODE=False
ENV POSTGRE_URL=postgresql://postgres:postgres@postgres/aquamark

EXPOSE 80

RUN ["pip3", "install", "-vU", "setuptools"]
RUN ["pip3", "install", "-r",  "./requirements.txt"]

#RUN /bin/bash -c ./config/config.sh

CMD ["python3", "./server/app.py"]