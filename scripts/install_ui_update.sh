#!/bin/sh
# Run only on the explicitly selected OpenWrt router; no network reconfiguration.
set -eu
umask 077
bundle=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
expected=${1:-}
case "$expected" in ''|*[!a-f0-9]*) echo 'Invalid manifest hash'; exit 2 ;; esac
[ "${#expected}" = 64 ] || exit 2
. /etc/openwrt_release
[ "$DISTRIB_RELEASE" = 25.12.6 ] || { echo 'Requires OpenWrt 25.12.6'; exit 3; }
[ "$(apk --print-arch)" = x86_64 ] || { echo 'Requires x86_64'; exit 3; }
cd "$bundle"
[ "$(sha256sum SHA256SUMS | cut -c1-64)" = "$expected" ] || { echo 'Manifest SHA256 mismatch'; exit 4; }
sha256sum -c SHA256SUMS
set --
while read -r hash name; do
	case "$name" in ''|*[!a-zA-Z0-9._+-]*) echo 'Invalid package filename'; exit 4 ;; esac
	case "$name" in *.apk) ;; *) exit 4 ;; esac
	set -- "$@" "$bundle/$name"
done < SHA256SUMS
[ "$#" = 6 ] || { echo 'Expected six packages'; exit 4; }
free=$(df -Pk /overlay | awk 'NR==2 {print $4}')
[ "$free" -ge 16384 ] || { echo 'Need at least 16 MiB free overlay space'; exit 5; }
backup=/root/home-ui-backups/0.2.0-$(date +%Y%m%d-%H%M%S)-$$
mkdir -p "$backup/cache"
chmod 0700 /root/home-ui-backups "$backup" "$backup/cache"
tar -czf "$backup/configs.tar.gz" /etc/config 2>/dev/null
uci -q get luci.main.mediaurlbase > "$backup/previous-theme" || true
printf '%s\n' 'Installing verified local packages...'
apk add --interactive=no --no-network --allow-untrusted "$@"
chmod 0600 /etc/config/homesmb
uci set luci.main.mediaurlbase=/luci-static/argon
uci set luci.themes.Argon=/luci-static/argon
uci commit luci
# Preserve old generated caches instead of deleting them.
for cache in /tmp/luci-indexcache* /tmp/luci-modulecache*; do
	[ -e "$cache" ] || [ -L "$cache" ] || continue
	mv "$cache" "$backup/cache/"
done
/etc/init.d/rpcd restart
/etc/init.d/uhttpd restart
printf 'HOME_UI_INSTALL_COMPLETE\nBackup: %s\n' "$backup"
printf 'Refresh LuCI. Open Services > Home services, Network > Common settings.\n'
