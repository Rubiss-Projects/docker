FROM lscr.io/linuxserver/transmission:4.1.3@sha256:4813745e2c721997d8849f5718786fd4406b3c656fbef479f87a161e51383cbd
RUN apk add --no-cache strace
LABEL diagnostic.role="transmission-linux-timing-v1"
HEALTHCHECK NONE
ENTRYPOINT ["python3"]
