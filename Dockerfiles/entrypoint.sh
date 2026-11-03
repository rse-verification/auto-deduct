#!/bin/sh
set -eu

# Explicit non-root --user launches (including verifier containers) need no remapping.
if [ "$(id -u)" != 0 ] || [ ! -w /etc/passwd ] || [ "${AUTODEDUCT_MATCH_WORKSPACE:-1}" = 0 ]; then
    exec "$@"
fi

uid=$(id -u dev)
gid=$(id -g dev)
# Docker exposes the bind mount owner's numeric identity inside the container.
if [ -d /work ]; then
    uid=$(stat -c %u /work)
    gid=$(stat -c %g /work)
fi

if ! getent group "$gid" >/dev/null; then
    groupadd --gid "$gid" autodeduct-host
fi
if ! getent passwd "$uid" >/dev/null; then
    useradd --no-create-home --uid "$uid" --gid "$gid" \
        --home-dir /home/dev --shell /bin/bash autodeduct-host
fi

# Leave mounted files and the installed toolchain ownership untouched.
chown "$uid:$gid" /home/dev
export HOME=/home/dev
exec setpriv --reuid="$uid" --regid="$gid" --clear-groups -- "$@"
