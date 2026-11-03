#!/bin/sh
set -eu

# Docker --user selects permissions; NSS supplies names for arbitrary numeric IDs.
uid=$(id -u)
gid=$(id -g)
if ! getent passwd "$uid" >/dev/null || ! getent group "$gid" >/dev/null; then
    accounts=$(mktemp -d /tmp/autodeduct-accounts.XXXXXX)
    cp /etc/passwd /etc/group "$accounts/"
    if ! getent passwd "$uid" >/dev/null; then
        printf 'autodeduct-%s:x:%s:%s:AutoDeduct:/home/dev:/bin/bash\n' \
            "$uid" "$uid" "$gid" >> "$accounts/passwd"
    fi
    if ! getent group "$gid" >/dev/null; then
        printf 'autodeduct-%s:x:%s:\n' "$gid" "$gid" >> "$accounts/group"
    fi
    export NSS_WRAPPER_PASSWD="$accounts/passwd" NSS_WRAPPER_GROUP="$accounts/group"
    export LD_PRELOAD="/usr/local/lib/libnss_wrapper.so${LD_PRELOAD:+:$LD_PRELOAD}"
fi

exec "$@"
