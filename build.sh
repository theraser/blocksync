#!/usr/bin/env bash

docker build --build-arg "TAG=3" --tag blocksync .
docker build --build-arg "TAG=3.8" --tag blocksync:3.8 .