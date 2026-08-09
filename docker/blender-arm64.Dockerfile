FROM ubuntu:26.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install --no-install-recommends --yes blender ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["blender"]
