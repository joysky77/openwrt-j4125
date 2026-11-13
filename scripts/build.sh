#!/usr/bin/env bash
set -euo pipefail
PROJECT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_SOURCE="${BUILD_SOURCE:-$PROJECT/build/openwrt}"
BUILD_LOGS="${BUILD_LOGS:-$PROJECT/artifacts/logs}"
FIRMWARE_OUTPUT="${FIRMWARE_OUTPUT:-$PROJECT/artifacts/firmware}"
mkdir -p "$BUILD_LOGS"
STAGE="${1:-all}"
case "$STAGE" in all|prepare|download|compile|collect) ;; *) exit 2 ;; esac
exec > >(tee -a "$BUILD_LOGS/build.log") 2>&1
trap 'result=$?; if [[ -f "$BUILD_SOURCE/.config" ]]; then cp "$BUILD_SOURCE/.config" "$BUILD_LOGS/resolved.config"; fi; exit "$result"' EXIT
if [[ "$STAGE" = all || "$STAGE" = prepare ]]; then
python3 "$PROJECT/scripts/project.py" prepare --source "$BUILD_SOURCE"
cd "$BUILD_SOURCE"
./scripts/feeds update -a
python3 - "$PROJECT/configs/build-lock.json" <<'PY'
import json, subprocess, sys
lock=json.load(open(sys.argv[1]))
for name, source in lock['feeds'].items():
    actual=subprocess.check_output(['git','-C','feeds/'+name,'rev-parse','HEAD'],text=True).strip()
    if actual != source['commit']:
        raise SystemExit('Feed commit mismatch: '+name)
PY
# Index all locked feeds, but install only selected recipes plus their
# dependencies. Installing every unrelated LuCI app can introduce upstream
# Kconfig cycles even when those apps are not selected for the firmware.
./scripts/feeds install -p passwall_packages chinadns-ng geoview tcping
./scripts/feeds install -p passwall2 luci-app-passwall2
python3 - "$PROJECT/configs/x86-64.config" <<'PY'
import re, subprocess, sys
text=open(sys.argv[1]).read()
packages=re.findall(r'^CONFIG_PACKAGE_([^=]+)=y$', text, re.M)
skip={'home-router-tools','luci-app-passwall2'}
# Kconfig suboptions are not standalone package recipes.
packages=[p for p in packages if p not in skip and not p.startswith(('kmod-', 'luci-app-passwall2_', 'dnsmasq_'))]
subprocess.run(['./scripts/feeds','install',*packages],check=True)
PY
python3 "$PROJECT/scripts/project.py" patch-transmission --source "$BUILD_SOURCE"
# Feed indexing can normalize .config before optional packages exist. Restore
# the requested seed after installing recipes, then resolve it exactly once.
cp "$PROJECT/configs/x86-64.config" .config
make defconfig
python3 "$PROJECT/scripts/project.py" check-config --source .config
./scripts/diffconfig.sh > "$BUILD_LOGS/diffconfig"
fi
cd "$BUILD_SOURCE"
if [[ "$STAGE" = all || "$STAGE" = download ]]; then
make download -j4
fi
if [[ "$STAGE" = all || "$STAGE" = compile ]]; then
# Keep parallelism conservative for Go/toolchain memory and network stability.
make -j3 V=s
fi
if [[ "$STAGE" = all || "$STAGE" = collect ]]; then
python3 "$PROJECT/scripts/project.py" collect --source "$BUILD_SOURCE" --output "$FIRMWARE_OUTPUT"
EXPANSION="$(dirname "$FIRMWARE_OUTPUT")/expansion"
mkdir -p "$EXPANSION"
tar -czf "$EXPANSION/matching-packages.tar.gz" bin/packages bin/targets/x86/64/packages
for archive in bin/targets/x86/64/*ImageBuilder* bin/targets/x86/64/*imagebuilder* bin/targets/x86/64/*sdk*; do
    [[ ! -f "$archive" ]] || cp "$archive" "$EXPANSION/"
done
cp "$PROJECT/configs/build-lock.json" "$EXPANSION/"
cp .config "$EXPANSION/resolved.config"
python3 - "$EXPANSION" <<'PY'
import hashlib, pathlib, sys
p=pathlib.Path(sys.argv[1])
with (p/'SHA256SUMS').open('w') as sums:
    for f in sorted(p.iterdir()):
        if f.is_file() and f.name != 'SHA256SUMS':
            with f.open('rb') as stream:
                sums.write(hashlib.file_digest(stream,'sha256').hexdigest()+'  '+f.name+'\n')
PY
printf 'Candidate built. Hardware, NAS and stability tests are NOT completed.\n'
fi
