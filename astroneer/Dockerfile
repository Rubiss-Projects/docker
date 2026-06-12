###########################################################
# Dockerfile that builds a astroneer Gameserver
###########################################################
FROM cm2network/steamcmd:root

ENV STEAMAPPID 728470
ENV STEAMAPP astroneer
ENV STEAMAPPDIR "${HOMEDIR}/${STEAMAPP}-dedicated"
COPY ./etc/entry.sh ${HOMEDIR}/entry.sh

RUN set -x \
	&& mkdir -p "${STEAMAPPDIR}" \
	&& chmod +x "${HOMEDIR}/entry.sh"
	
ENV PORT=8777

USER ${USER}

VOLUME ${STEAMAPPDIR}

WORKDIR ${HOMEDIR}

CMD ["bash", "entry.sh"]

# Expose ports
EXPOSE 27015/tcp \
	27015/udp \
	27020/udp
