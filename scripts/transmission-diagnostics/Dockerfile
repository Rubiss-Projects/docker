FROM lscr.io/linuxserver/transmission:4.1.3@sha256:d6caecad406774a18511be7bfa99ba5070c17a3bdd7a5d73091651841603273c
RUN apk add --no-cache strace
LABEL diagnostic.role="transmission-linux-timing-v1"
HEALTHCHECK NONE
ENTRYPOINT ["python3"]
