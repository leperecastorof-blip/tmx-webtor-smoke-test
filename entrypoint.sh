#!/bin/sh
# Runtime only. No creation/deletion of links at /, ever.
set -eu
fail() { printf '%s\n' "TMX_WEBTOR_GUARD:$1" >&2; exit 78; }
[ "$$" -eq 1 ] || fail NOT_CONTAINER_ENTRYPOINT
[ -f /etc/tmx-webtor/image-sentinel ] || fail IMAGE_SENTINEL_MISSING
[ "$(cat /etc/tmx-webtor/image-sentinel)" = 'tmx-webtor-confined-v2' ] || fail WRONG_IMAGE
[ -f /.dockerenv ] || [ -f /run/.containerenv ] || fail CONTAINER_MARKER_MISSING
ROOT=/var/lib/webtor
[ "${PERSISTENT_DISK_PATH:-$ROOT}" = "$ROOT" ] || fail UNEXPECTED_STORAGE_PATH
[ -d "$ROOT" ] && [ ! -L "$ROOT" ] || fail STORAGE_NOT_DIRECTORY
[ "$(readlink -f "$ROOT")" = "$ROOT" ] || fail STORAGE_PATH_REDIRECTED
awk '$5=="/var/lib/webtor" && $6 ~ /(^|,)rw(,|$)/ {ok=1} END {exit !ok}' /proc/self/mountinfo || fail EXPLICIT_RW_VOLUME_REQUIRED
[ -n "${ADMIN_PASSWORD:-}" ] && [ "${#ADMIN_PASSWORD}" -ge 24 ] || fail ADMIN_SECRET_REQUIRED
[ -n "${PG_PASSWORD:-}" ] && [ "${#PG_PASSWORD}" -ge 24 ] || fail DATABASE_SECRET_REQUIRED
[ -n "${AWS_ACCESS_KEY_ID:-}" ] && [ -n "${AWS_SECRET_ACCESS_KEY:-}" ] || fail STORAGE_SECRETS_REQUIRED
[ "${ONLY_AUTHORIZED:-true}" = true ] || fail AUTH_CANNOT_BE_DISABLED
[ "${EMBED_ONLY_AUTHORIZED:-true}" = true ] || fail EMBED_AUTH_CANNOT_BE_DISABLED
DOMAIN="${DOMAIN:-${RENDER_EXTERNAL_URL:-}}"
case "$DOMAIN" in https://?*) ;; *) fail HTTPS_DOMAIN_REQUIRED ;; esac
export DOMAIN ONLY_AUTHORIZED=true EMBED_ONLY_AUTHORIZED=true
# Validate all paths before touching any of them. Symlinks are image-build artifacts.
for name in data pgdata storage; do
 [ -L "/$name" ] && [ "$(readlink "/$name")" = "$ROOT/$name" ] || fail WRONG_IMAGE_STORAGE_LINK
 [ ! -L "$ROOT/$name" ] || fail VOLUME_CHILD_SYMLINK
 if [ -e "$ROOT/$name" ]; then
  [ -d "$ROOT/$name" ] && [ "$(readlink -f "$ROOT/$name")" = "$ROOT/$name" ] || fail UNSAFE_VOLUME_CHILD
 fi
done
id postgres >/dev/null 2>&1 || fail POSTGRES_USER_MISSING
umask 077
for name in data pgdata storage; do mkdir -p "$ROOT/$name"; done
# Do not recursively traverse a pre-existing volume or mask permission errors.
chown postgres:postgres "$ROOT/pgdata"
chmod 700 "$ROOT/pgdata"
# Only a constant is logged. No environment values, paths, keys or passwords.
printf '%s\n' 'TMX_WEBTOR_STORAGE_READY'
# App-specific runtime files stay inside the declared application data volume.
mkdir -p "$ROOT/runtime/home" "$ROOT/runtime/cache" "$ROOT/runtime/share" /run/nginx
export HOME="$ROOT/runtime/home"
export XDG_CACHE_HOME="$ROOT/runtime/cache"
export XDG_DATA_HOME="$ROOT/runtime/share"
export PGDATA_DIR="$ROOT/pgdata"
exec /init
