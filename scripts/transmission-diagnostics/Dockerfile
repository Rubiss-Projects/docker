FROM lscr.io/linuxserver/transmission:4.1.4@sha256:5b3c27a96c8a37c878a525ebf377a32032c3a3acfe845ecaa7c3eb10b09c2caa
RUN apk add --no-cache strace
LABEL diagnostic.role="transmission-linux-timing-v1"
HEALTHCHECK NONE
ENTRYPOINT ["python3"]
