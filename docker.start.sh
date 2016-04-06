#!/usr/bin/env bash
docker run -d -P --name putioSync -v $PWD/test:/downloads putio-sync:latest