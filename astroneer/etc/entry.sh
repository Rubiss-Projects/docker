#!/bin/bash
mkdir -p "${STEAMAPPDIR}" || true  

bash "${STEAMCMDDIR}/steamcmd.sh" +login anonymous \
				+force_install_dir "${STEAMAPPDIR}" \
				+app_update "${STEAMAPPID}" \
				+quit

# Setup required configurations
# echo "[URL]
# Port=${PORT}" >> "${STEAMAPPDIR}/astro/saved/config/windows server/engine.ini"
# echo "PublicIP=${PUBLIC_IP}" >> "${STEAMAPPDIR}/astro/saved/config/windows server/astroserversettings.ini"
# echo "OwnerName=${OWNERNAME}
# OwnerGuid=0" >> "${STEAMAPPDIR}/astro/saved/config/windows server/astroserversettings.ini"

# bash "${STEAMAPPDIR}/SquadGameServer.sh" \
# 			Port="${PORT}" \
# 			QueryPort="${QUERYPORT}" \
# 			RCONPORT="${RCONPORT}" \
# 			FIXEDMAXPLAYERS="${FIXEDMAXPLAYERS}" \
# 			FIXEDMAXTICKRATE="${FIXEDMAXTICKRATE}" \
# 			RANDOM="${RANDOM}"