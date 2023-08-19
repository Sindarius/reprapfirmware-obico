#!/bin/bash

set -e

JANUS_ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
echo $JANUS_ROOT_DIR
RUNTIME_JANUS_ETC_DIR="${JANUS_ROOT_DIR}/runtime/etc/janus"

#used for raspberry pi
#. "${JANUS_ROOT_DIR}/../utils.sh"
#PRECOMPILED_DIR="${JANUS_ROOT_DIR}/precomplied/debian.$( debian_variant )"

#used for jetson nano
PRECOMPILED_DIR="${JANUS_ROOT_DIR}/precomplied/ubuntu.18.04"

if [ -d "${PRECOMPILED_DIR}" ]; then
  echo "Entering THEN"
  lib_janus_dir="${PRECOMPILED_DIR}/lib/janus"
  LIB_PATH="${PRECOMPILED_DIR}/lib:${LD_LIBRARY_PATH}"
  JANUS_CMD="${PRECOMPILED_DIR}/bin/janus"
else
  LIB_PATH="${LD_LIBRARY_PATH}"
  JANUS_CMD="janus"
fi

_term() {
  kill -TERM "$child" 2>/dev/null
}

trap _term SIGTERM

LD_LIBRARY_PATH="${LIB_PATH}" nice "${JANUS_CMD}" -o --stun-server=stun.l.google.com:19302 --configs-folder="${RUNTIME_JANUS_ETC_DIR}" &
echo $LD_LIBRARY_PATH

child=$!
wait "$child"
