#!/bin/bash

trap 'umount .testdb' EXIT

mount -t tmpfs -o size=512M tmpfs .testdb
docker-compose run --rm test "$@"
