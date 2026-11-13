#!/usr/bin/env python3
"""Validate and prepare a pinned OpenWrt build; standard library only."""
import argparse
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True)


def lock_data():
    return json.loads((ROOT / 'configs/build-lock.json').read_text(encoding='utf-8'))


def required():
    return [s.strip() for s in (ROOT / 'configs/required-packages.txt').read_text(encoding='utf-8').splitlines()
            if s.strip() and not s.startswith('#')]


def validate():
    lock = lock_data()
    for source in [lock['openwrt'], *lock['feeds'].values()]:
        if not re.fullmatch(r'[0-9a-f]{40}', source['commit']):
            raise ValueError('Sources must use full immutable commit IDs')
        if not re.fullmatch(r'https://github.com/[\w.-]+/[\w.-]+\.git', source['url']):
            raise ValueError('Untrusted source URL')
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-rc[0-9]+)?', lock['firmware_version']):
        raise ValueError('Invalid firmware version')
    config = (ROOT / 'configs/x86-64.config').read_text(encoding='utf-8')
    if 'CONFIG_TARGET_ROOTFS_PARTSIZE=4096' not in config:
        raise ValueError('Unexpected root partition size')
    if len(required()) != len(set(required())):
        raise ValueError('Duplicate required packages')
    for path in ROOT.rglob('*'):
        if not path.is_file() or any(p in ('.git', 'build', 'artifacts', '.venv') for p in path.parts):
            continue
        if path.name.startswith('storage-plan-'):
            continue
        if path.suffix in ('.sh', '.py', '.json', '.yml') and b'\r\n' in path.read_bytes():
            raise ValueError(f'Expected LF line endings: {path}')
    print('Build lock and project configuration validated.')


def prepare(destination):
    validate()
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Build source destination must not exist; preserve previous builds')
    lock = lock_data()
    destination.mkdir(parents=True)
    run(['git', 'init', str(destination)])
    run(['git', 'remote', 'add', 'origin', lock['openwrt']['url']], destination)
    run(['git', 'fetch', '--depth=1', 'origin', lock['openwrt']['commit']], destination)
    run(['git', 'checkout', '--detach', 'FETCH_HEAD'], destination)
    feed_lines = [f"src-git {name} {source['url']}^{source['commit']}"
                  for name, source in lock['feeds'].items()]
    (destination / 'feeds.conf').write_text('\n'.join(feed_lines) + '\n')
    shutil.copyfile(ROOT / 'configs/x86-64.config', destination / '.config')
    shutil.copytree(ROOT / 'packages/home-router-tools', destination / 'package/home-router-tools')
    print(f'Prepared immutable source: {destination}')


def check_config(path):
    config = Path(path).read_text(encoding='utf-8')
    for prohibited in ('CONFIG_ALL_NONSHARED=y', 'CONFIG_ALL_KMODS=y', 'CONFIG_ALL=y'):
        if prohibited + '\n' in config:
            raise ValueError('Unexpected all-packages build: ' + prohibited)
    missing = [p for p in required() if f'CONFIG_PACKAGE_{p}=y\n' not in config]
    for symbol in ('CONFIG_TARGET_x86=y', 'CONFIG_TARGET_x86_64=y',
                   'CONFIG_GRUB_IMAGES=y', 'CONFIG_GRUB_EFI_IMAGES=y',
                   'CONFIG_TARGET_ROOTFS_SQUASHFS=y',
                   'CONFIG_TARGET_KERNEL_PARTSIZE=256', 'CONFIG_TARGET_ROOTFS_PARTSIZE=4096'):
        if symbol + '\n' not in config:
            missing.append(symbol)
    if missing:
        raise ValueError('Required selections absent after defconfig: ' + ', '.join(missing))
    print(f'All {len(required())} required packages selected in resolved configuration.')


def image_partitions(path):
    with gzip.open(path, 'rb') as image:
        header = image.read(65536)
    if header[510:512] != b'\x55\xaa':
        raise ValueError('Invalid image MBR signature')
    if header[512:520] == b'EFI PART':
        entries_lba = struct.unpack_from('<Q', header, 512 + 72)[0]
        entry_size = struct.unpack_from('<I', header, 512 + 84)[0]
        if entry_size < 128 or entries_lba * 512 + entry_size * 2 > len(header):
            raise ValueError('Unsupported GPT entries')
        sizes = []
        for i in range(2):
            start, end = struct.unpack_from('<QQ', header, entries_lba * 512 + entry_size * i + 32)
            sizes.append((end - start + 1) * 512)
    else:
        sizes = [struct.unpack_from('<I', header, 446 + 16 * i + 12)[0] * 512 for i in range(2)]
    if sizes != [256 * 1024**2, 4096 * 1024**2]:
        raise ValueError(f'Unexpected boot/root partition sizes: {sizes}')
    return sizes


def patch_transmission(source):
    script = Path(source) / 'feeds/packages/net/transmission/files/transmission.init'
    text = script.read_text(encoding='utf-8')
    anchor = 'transmission() {\n\tlocal cfg="$1"\n'
    if text.count(anchor) != 1:
        raise ValueError('Upstream Transmission init changed; review storage guard placement')
    guard = '\t/usr/sbin/home-storage-check || { logger -t transmission "Storage guard rejected start"; return 1; }\n'
    script.write_text(text.replace(anchor, anchor + guard), encoding='utf-8')


def collect(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    target = source / 'bin/targets/x86/64'
    manifests = list(target.glob('*.manifest'))
    if not manifests:
        raise ValueError('No firmware manifest; refusing to label build successful')
    for manifest in manifests:
        installed = {line.split(' - ', 1)[0].strip() for line in manifest.read_text(encoding='utf-8').splitlines()}
        missing = set(required()) - installed
        if missing:
            raise ValueError(f'Manifest {manifest.name} missing: {sorted(missing)}')
    images = list(target.glob('*squashfs-combined*.img.gz'))
    if not any('combined-efi' in p.name for p in images) or not any('combined.img' in p.name for p in images):
        raise ValueError('Both UEFI and Legacy combined disk images are required')
    partition_report = {p.name: image_partitions(p) for p in images}
    output.mkdir(parents=True, exist_ok=True)
    version = lock_data()['firmware_version']
    for file in images:
        shutil.copyfile(file, output / f'home-router-{version}-{file.name}')
    metadata = output / 'metadata'
    metadata.mkdir(exist_ok=True)
    for file in target.iterdir():
        if file.is_file() and not file.name.endswith('.img.gz'):
            shutil.copy2(file, metadata / file.name)
    shutil.copy2(source / '.config', metadata / 'resolved.config')
    shutil.copy2(ROOT / 'configs/build-lock.json', metadata / 'build-lock.json')
    (metadata / 'image-partitions.json').write_text(json.dumps(partition_report, indent=2) + '\n')
    shutil.copy2(ROOT / 'README.md', output / 'README.md')
    shutil.copytree(ROOT / 'docs', output / 'docs', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('定制方案-*'))
    run(['sh', '-c', './scripts/diffconfig.sh > "$1"', 'sh', str(metadata / 'diffconfig')], source)
    sources = {name: subprocess.check_output(['git', '-C', str(source / 'feeds' / name),
               'rev-parse', 'HEAD'], text=True).strip() for name in lock_data()['feeds']}
    (metadata / 'actual-feeds.json').write_text(json.dumps(sources, indent=2) + '\n')
    (metadata / 'validation-status.json').write_text(json.dumps({
        'build_manifest_validated': True, 'hardware_tested': False,
        'nas_configured': False, 'child_devices_configured': False,
        'stability_soak_passed': False, 'release_channel': 'candidate'}, indent=2) + '\n')
    sums = []
    for file in sorted(output.rglob('*')):
        if file.is_file() and file.name != 'SHA256SUMS':
            sums.append(f'{hashlib.file_digest(file.open("rb"), "sha256").hexdigest()}  {file.relative_to(output).as_posix()}')
    (output / 'SHA256SUMS').write_text('\n'.join(sums) + '\n')
    print(f'Collected {len(images)} candidate images; hardware validation remains pending.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('validate', 'prepare', 'check-config', 'collect', 'patch-transmission'))
    parser.add_argument('--source')
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.command == 'validate':
        validate()
    elif args.command == 'prepare':
        prepare(args.source)
    elif args.command == 'check-config':
        check_config(args.source)
    elif args.command == 'patch-transmission':
        patch_transmission(args.source)
    else:
        collect(args.source, args.output)


if __name__ == '__main__':
    main()
