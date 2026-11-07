FROM lscr.io/linuxserver/transmission:4.1.4@sha256:fb8fe625941cf15eb69aba4e5c0a678e035ddb11605fd85af4516a4e641f2687
RUN apk add --no-cache strace
LABEL diagnostic.role="transmission-linux-timing-v1"
HEALTHCHECK NONE
ENTRYPOINT ["python3"]
