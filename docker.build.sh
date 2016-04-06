#!/usr/bin/env bash

export DOWNLOAD_DIR=`pwd`/test
export CONFIG_DIR=.

docker-compose build
docker tag `docker images | grep putiodownloader_putio-sync | awk '{ print $3 }'` devclinton/putio-sync:latest
docker push devclinton/putio-sync:latest