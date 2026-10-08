#!/bin/sh
set -eu

SOURCE=${1:-}
CONFIG_ROOT=${2:-/config}
DOMAIN=cisco_catalyst
ACTIVE="$CONFIG_ROOT/custom_components/$DOMAIN"
BACKUP_ROOT="$CONFIG_ROOT/${DOMAIN}_backups"
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP="$BACKUP_ROOT/${DOMAIN}.pre-stage-$STAMP"
STAGE="$CONFIG_ROOT/.${DOMAIN}_stage-$STAMP"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

[ -n "$SOURCE" ] || fail "usage: $0 SOURCE_DIR [CONFIG_ROOT]"
[ -d "$SOURCE" ] || fail "source directory not found: $SOURCE"
[ -f "$SOURCE/manifest.json" ] || fail "source manifest.json missing"
[ -d "$CONFIG_ROOT/custom_components" ] || fail "custom_components not found under $CONFIG_ROOT"

case "$BACKUP_ROOT" in
    "$CONFIG_ROOT/custom_components"|"$CONFIG_ROOT/custom_components/"*)
        fail "backup root must not be inside custom_components"
        ;;
esac

mkdir -p "$BACKUP_ROOT"
rm -rf "$STAGE"
cp -a "$SOURCE" "$STAGE"
rm -rf "$STAGE/__pycache__"

[ -f "$STAGE/manifest.json" ] || fail "staged manifest.json missing"

echo "---- START CISCO SAFE STAGING ----"
echo "Source: $SOURCE"
echo "Active: $ACTIVE"
echo "Backup root: $BACKUP_ROOT"
echo
echo "Staged manifest:"
cat "$STAGE/manifest.json"

if [ -d "$ACTIVE" ]; then
    cp -a "$ACTIVE" "$BACKUP"
    echo
echo "Preserved active integration at:"
    echo "$BACKUP"
fi

rm -rf "$ACTIVE"
mv "$STAGE" "$ACTIVE"

echo
echo "Cisco directories directly under custom_components:"
FOUND=$(find "$CONFIG_ROOT/custom_components" -maxdepth 1 -mindepth 1 -type d -name "${DOMAIN}*" -print)
printf '%s\n' "$FOUND"

[ "$FOUND" = "$ACTIVE" ] || fail "unsafe Cisco backup/staging directory remains under custom_components"

echo
echo "Active manifest after staging:"
cat "$ACTIVE/manifest.json"
echo
echo "Staging complete. Home Assistant was not restarted."
echo "**** END CISCO SAFE STAGING ****"


