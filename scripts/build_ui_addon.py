#!/usr/bin/env python3
"""Package architecture-independent LuCI files using the matching SDK apk tool."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def build(sdk, output, staging_root=None):
    if os.geteuid() != 0:
        raise RuntimeError('Use root for package file ownership; no host installation is performed')
    sdk, output = Path(sdk).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    tool = sdk / 'staging_dir/host/bin/apk'
    lock = json.loads((ROOT / 'configs/ui-addon-lock.json').read_text())
    for spec in lock['packages']:
        target = output / spec['name']
        if not target.exists():
            request = urllib.request.Request(spec['url'], headers={'User-Agent': 'home-router-build/0.2.0'})
            with urllib.request.urlopen(request, timeout=90) as response, target.open('xb') as stream:
                shutil.copyfileobj(response, stream)
        if digest(target) != spec['sha256']:
            raise RuntimeError('Upstream package SHA256 mismatch: ' + spec['name'])
    packages = [
        ('luci-app-home-ui', '0.2.0-r1', 'luci-base luci-compat cifsmount kmod-fs-cifs flock coreutils-timeout'),
        ('luci-app-home-zerotier', '0.1.1-r1', 'luci-base luci-compat zerotier'),
    ]
    for name, version, depends in packages:
        # Preserve processing directories; no recursive cleanup of host files.
        stage = Path(tempfile.mkdtemp(prefix=name + '-', dir=staging_root))
        shutil.copytree(ROOT / 'packages' / name / 'files', stage, dirs_exist_ok=True)
        metadata = stage / 'lib/apk/packages'
        metadata.mkdir(parents=True, exist_ok=True)
        if name == 'luci-app-home-ui':
            (metadata / (name + '.conffiles')).write_text('/etc/config/homesmb\n')
            (metadata / (name + '.conffiles_static')).write_text('/etc/config/homesmb ' + digest(stage / 'etc/config/homesmb') + '\n')
        listing = sorted('/' + str(p.relative_to(stage)) for p in stage.rglob('*') if p.is_file())
        (metadata / (name + '.list')).write_text('\n'.join(listing) + '\n')
        for path in [stage, *stage.rglob('*')]:
            os.chown(path, 0, 0)
            mode = 0o755 if path.is_dir() else 0o644
            if path.name == 'home-smb' and not path.is_dir():
                mode = 0o755
            if path == stage / 'etc/config/homesmb':
                mode = 0o600
            path.chmod(mode)
        target = output / (name + '-' + version + '.apk')
        if target.exists():
            raise RuntimeError('Preserve old build; use a new output directory: ' + str(target))
        subprocess.run([str(tool), 'mkpkg', '--info', 'name:' + name,
                        '--info', 'version:' + version, '--info', 'arch:noarch',
                        '--info', 'license:MIT', '--info', 'description:Home router management UI',
                        '--info', 'depends:' + depends, '--files', str(stage), '--output', str(target)], check=True)
    sums = []
    for package in sorted(output.glob('*.apk')):
        subprocess.run([str(tool), 'verify', '--allow-untrusted', str(package)], check=True)
        sums.append(digest(package) + '  ' + package.name)
    (output / 'SHA256SUMS').write_text('\n'.join(sums) + '\n')
    shutil.copyfile(ROOT / 'configs/ui-addon-lock.json', output / 'ui-addon-lock.json')
    print('UI update bundle created:', output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--sdk', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--staging-root')
    args = parser.parse_args()
    build(args.sdk, args.output, args.staging_root)
