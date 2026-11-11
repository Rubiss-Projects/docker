FROM lscr.io/linuxserver/transmission:4.1.4@sha256:aaf349cd859ca9d5f34f394c56b8097c267a513283698adc4d07ee61d7cb1a85
RUN apk add --no-cache strace
LABEL diagnostic.role="transmission-linux-timing-v1"
HEALTHCHECK NONE
ENTRYPOINT ["python3"]
