FROM ubuntu:14.04

MAINTAINER Alex Fraser <alex@vpac-innovations.com.au>

RUN DEBIAN_FRONTEND=noninteractive \
    apt-get update && \
    apt-get install -y \
        npm \
        nodejs \
        build-essential \
        python3 \
        virtualenvwrapper \
        python3-pip \
        git \
        --no-install-recommends && \
    which node || sudo apt-get install -y nodejs-legacy && \
    npm install -g bower && \
    rm -rf /var/lib/apt/lists/*

#ENV MONGO_URL mongodb://[username:password@]host1[:port1][,host2[:port2],...[,hostN[:portN]]][/[database][?options]]
ENV MONGO_URL mongodb://mongodb/aquamark

COPY ./ /usr/share/aquamark
COPY config/config.sh.DOCKER_SAMPLE /usr/share/aquamark/config/config.sh

WORKDIR /usr/share/aquamark

ENV PORT=80 DEV_MODE=False
EXPOSE 80

RUN ["/usr/share/aquamark/start.sh", "install"]

CMD ["/usr/share/aquamark/start.sh"]
