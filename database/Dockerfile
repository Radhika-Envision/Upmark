FROM ubuntu:14.04

MAINTAINER Jin Park <forjin@vpac-innovations.com.au>

RUN DEBIAN_FRONTEND=noninteractive \
    apt-get update && \
    apt-get install -y \
    python3-pip \
    cron

RUN pip3 install boto3

RUN mkdir -p /root/.aws
COPY config /root/.aws/config
COPY credentials /root/.aws/credentials
COPY backup.py /root/backup.py
COPY cron_backup /root/cron_backup

RUN crontab /root/cron_backup
CMD ["cron", "-f", "/root/cron_backup"]
