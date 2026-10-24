FROM lscr.io/linuxserver/transmission:4.1.3@sha256:55aaeedf9fc354d34136387e15ee0ba4679096f20398dd2875867e5cd5cf8be5
RUN apk add --no-cache strace
LABEL diagnostic.role="transmission-linux-timing-v1"
HEALTHCHECK NONE
ENTRYPOINT ["python3"]
