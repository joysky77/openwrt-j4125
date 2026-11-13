#!/usr/bin/env bash
set -euo pipefail
PROJECT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_SOURCE="${BUILD_SOURCE:-$PROJECT/build/openwrt}"
BUILD_LOGS="${BUILD_LOGS:-$PROJECT/artifacts/logs}"
FIRMWARE_OUTPUT="${FIRMWARE_OUTPUT:-$PROJECT/artifacts/firmware}"
mkdir -p "$BUILD_LOGS"
exec > >(tee -a "$BUILD_LOGS/build.log") 2>&1
trap 'result=$?; if [[ -f "$BUILD_SOURCE/.config" ]]; then cp "$BUILD_SOURCE/.config" "$BUILD_LOGS/resolved.config"; fi; exit "$result"' EXIT
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
./scripts/feeds install -a -p packages
./scripts/feeds install -a -p luci
./scripts/feeds install -a -p routing
./scripts/feeds install -f -a -p passwall_packages
./scripts/feeds install -a -p passwall2
make defconfig
python3 "$PROJECT/scripts/project.py" check-config --source .config
./scripts/diffconfig.sh > "$BUILD_LOGS/diffconfig"
make download -j4
# Keep parallelism conservative for Go/toolchain memory and network stability.
make -j3 V=s
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
