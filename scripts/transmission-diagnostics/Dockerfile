FROM lscr.io/linuxserver/transmission:4.1.3@sha256:1a12fef3c89eca48b7be9e7d36b17b4eb4e1bcf5e1ee7fbf372e3a38b562939d
RUN apk add --no-cache strace
LABEL diagnostic.role="transmission-linux-timing-v1"
HEALTHCHECK NONE
ENTRYPOINT ["python3"]
