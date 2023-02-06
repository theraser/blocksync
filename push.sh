#!/usr/bin/env bash

docker buildx create --name crossbuilder --driver docker-container --bootstrap --use
DOCKER_BUILDKIT=1 docker buildx build --platform "linux/amd64,linux/386,linux/arm64/v8,linux/arm/v5,linux/arm/v7,linux/s390x,linux/ppc64le" --build-arg "TAG=3" --tag corycarson/blocksync:latest --push .
DOCKER_BUILDKIT=1 docker buildx build --platform "linux/amd64,linux/386,linux/arm64/v8,linux/arm/v5,linux/arm/v7,linux/s390x,linux/ppc64le" --build-arg "TAG=3.8" --tag corycarson/blocksync:3.8 --push .
