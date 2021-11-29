#!/usr/bin/env bash

docker build --build-arg "TAG=3" --tag blocksync:3 .
docker build --build-arg "TAG=3.8" --tag blocksync:3.8 .
docker build --build-arg "TAG=2.7" --tag blocksync:2.7 .