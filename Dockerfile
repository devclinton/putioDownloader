FROM debian:jessie

MAINTAINER Clinton  Collins version 0.1

RUN mkdir /downloads
VOLUME /downloads

RUN apt-get update -y && apt-get install -y python3 libcurl4-openssl-dev python3-dev python3-pip libssl-dev  && apt-get clean && rm -rf /var/lib/apt/lists/*
ADD *.py /opt/putioSync/
WORKDIR /opt/putioSync
RUN pip3 install .
CMD python3 putioSync.py