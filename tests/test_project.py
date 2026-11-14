import contextlib
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import struct
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('project', ROOT / 'scripts/project.py')
project = importlib.util.module_from_spec(spec)
spec.loader.exec_module(project)
smoke_spec = importlib.util.spec_from_file_location('smoke_boot', ROOT/'scripts/smoke_boot.py')
smoke = importlib.util.module_from_spec(smoke_spec)
smoke_spec.loader.exec_module(smoke)


def fixture():
    # Preserve generated fixtures instead of deleting files on the user's host.
    directory = ROOT / 'artifacts/test-fixtures' / uuid.uuid4().hex
    directory.mkdir(parents=True)
    return directory


class BuildChecks(unittest.TestCase):
    def test_smoke_download_uses_one_exact_artifact_without_nested_pattern_directory(self):
        workflow = (ROOT/'.github/workflows/smoke.yml').read_text(encoding='utf-8')
        self.assertIn('--name "$artifact" --dir artifacts/smoke-input', workflow)
        self.assertNotIn('--pattern', workflow)
        self.assertIn('workflow_dispatch:', workflow)

    def test_guest_checks_wait_for_initialization_and_execute_real_policy(self):
        script = (ROOT/'scripts/smoke_boot.py').read_text(encoding='utf-8')
        self.assertIn('uci -q get luci.home_status.command', script)
        self.assertIn("date -s '2026-01-01 00:01:00'", script)
        self.assertIn("date -s '2026-01-01 07:01:00'", script)
        self.assertIn('nft list table inet home_child', script)

    def test_gzip_fwtool_trailer_is_not_treated_as_another_gzip_member(self):
        directory = fixture()
        source = directory/'input.img.gz'
        payload = b'firmware' * 1024
        source.write_bytes(gzip.compress(payload) + b'fwtool-metadata')
        target = directory/'output.img'
        smoke.decompress_image(source, target, minimum_size=1)
        self.assertEqual(target.read_bytes(), payload)

    def test_truncated_gzip_is_rejected(self):
        directory = fixture()
        source = directory/'input.img.gz'
        source.write_bytes(gzip.compress(b'firmware')[:-4])
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            smoke.decompress_image(source, directory/'output.img', minimum_size=1)

    def test_lock_is_immutable(self):
        with contextlib.redirect_stdout(io.StringIO()):
            project.validate()

    def test_missing_required_package_is_a_failure(self):
        with self.assertRaisesRegex(ValueError, 'Required selections absent'):
            project.check_config(ROOT / 'README.md')

    def test_all_modules_build_is_rejected(self):
        file = fixture() / 'resolved.config'
        file.write_text('CONFIG_ALL_KMODS=y\n')
        with self.assertRaisesRegex(ValueError, 'all-packages'):
            project.check_config(file)

    def test_mbr_partition_size_is_verified(self):
        header = bytearray(65536)
        header[510:512] = b'\x55\xaa'
        struct.pack_into('<I', header, 446+12, 256*2048)
        struct.pack_into('<I', header, 462+12, 4096*2048)
        file = fixture() / 'image.img.gz'
        with gzip.open(file, 'wb') as stream:
            stream.write(header)
        self.assertEqual(project.image_partitions(file), [256*1024**2, 4096*1024**2])

    def test_wrong_partition_size_is_rejected(self):
        file = fixture() / 'bad.img.gz'
        with gzip.open(file, 'wb') as stream:
            stream.write(bytes(65536))
        with self.assertRaisesRegex(ValueError, 'signature'):
            project.image_partitions(file)

    def test_gpt_partition_size_is_verified(self):
        header = bytearray(65536)
        header[510:512] = b'\x55\xaa'
        header[512:520] = b'EFI PART'
        struct.pack_into('<Q', header, 512+72, 2)
        struct.pack_into('<I', header, 512+84, 128)
        struct.pack_into('<QQ', header, 1024+32, 2048, 2048+256*2048-1)
        struct.pack_into('<QQ', header, 1152+32, 526336, 526336+4096*2048-1)
        file = fixture() / 'efi.img.gz'
        with gzip.open(file, 'wb') as stream:
            stream.write(header)
        self.assertEqual(project.image_partitions(file), [256*1024**2, 4096*1024**2])

    def test_transmission_guard_is_before_any_directory_creation(self):
        directory = fixture()
        file = directory / 'feeds/packages/net/transmission/files/transmission.init'
        file.parent.mkdir(parents=True)
        file.write_text('transmission() {\n\tlocal cfg="$1"\n\tmkdir -p "$download_dir"\n}\n')
        project.patch_transmission(directory)
        content = file.read_text(encoding='utf-8')
        self.assertLess(content.index('home-storage-check'), content.index('mkdir'))
        with self.assertRaisesRegex(ValueError, 'changed'):
            # An unexpected upstream template must not be silently patched.
            file.write_text('other_function() {}\n')
            project.patch_transmission(directory)

    def test_collect_rejects_no_firmware(self):
        directory = fixture()
        (directory / 'bin/targets/x86/64').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'No firmware manifest'):
            project.collect(directory, directory / 'output')

    def test_collect_rejects_incomplete_manifest(self):
        directory = fixture()
        target = directory / 'bin/targets/x86/64'
        target.mkdir(parents=True)
        (target / 'bad.manifest').write_text('luci - 1.0\n')
        with self.assertRaisesRegex(ValueError, 'missing:'):
            project.collect(directory, directory / 'output')

    def test_no_private_files_in_workflow(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text(encoding='utf-8')
        self.assertNotIn('secrets.', workflow)
        self.assertNotIn('schedule:', workflow)
        self.assertIn('contents: read', workflow)
        for sha in project.lock_data()['actions'].values():
            self.assertIn(sha, workflow)

    def test_seed_is_restored_after_feed_install_before_defconfig(self):
        script = (ROOT/'scripts/build.sh').read_text(encoding='utf-8')
        restore = script.index('cp "$PROJECT/configs/x86-64.config" .config')
        self.assertGreater(restore, script.index('patch-transmission'))
        self.assertLess(restore, script.index('make defconfig'))

    def test_downloads_are_not_enabled_before_mount_configuration(self):
        defaults = (ROOT / 'packages/home-router-tools/files/etc/uci-defaults/90-home-router').read_text(encoding='utf-8')
        self.assertIn("transmission.@transmission[0].enabled='0'", defaults)
        self.assertIn('/mnt/nas-downloads/incomplete', defaults)
        self.assertNotIn('mkfs', defaults)
        self.assertNotIn('/dev/sda', defaults)

    def test_status_command_uses_upstream_luci_namespace_and_requires_login(self):
        defaults = (ROOT / 'packages/home-router-tools/files/etc/uci-defaults/90-home-router').read_text(encoding='utf-8')
        self.assertIn("luci.home_status='command'", defaults)
        self.assertIn("luci.home_status.public='0'", defaults)
        self.assertIn("luci.home_status.param='0'", defaults)


@unittest.skipIf(os.name == 'nt', 'POSIX shell runtime tests run on Linux')
class ChildRules(unittest.TestCase):
    def execute(self, *, enabled='1', resume='7', mac='AA:BB:CC:DD:EE:FF', hour='00', lan='br-lan', exists=False):
        directory = fixture()
        commands = {
            'uci': '#!/usr/bin/env python3\nimport os,sys\nk=sys.argv[-1].split(".")[-1]\nv={"enabled":"ENABLED","resume_hour":"RESUME","mac":"MAC","lan_device":"LAN"}\nprint(os.environ.get(v.get(k,""),""))\n',
            'date': '#!/bin/sh\nprintf "%s\\n" "$HOUR"\n',
            'nft': '#!/bin/sh\nif [ "$1" = list ]; then [ "$EXISTS" = 1 ]; elif [ "$1" = -f ]; then cat; else printf "%s\\n" "$*"; fi\n',
        }
        for name, content in commands.items():
            path = directory / name
            path.write_text(content)
            path.chmod(0o755)
        env = dict(os.environ, PATH=str(directory)+os.pathsep+os.environ['PATH'],
                   ENABLED=enabled, RESUME=resume, MAC=mac, HOUR=hour, LAN=lan,
                   EXISTS=str(int(exists)))
        return subprocess.run(['sh', str(ROOT / 'packages/home-router-tools/files/usr/sbin/home-child-policy')],
                              env=env, text=True, capture_output=True)

    def test_midnight_blocks_ipv4_and_ipv6_before_proxy(self):
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('table inet home_child', result.stdout)
        self.assertIn('priority -310', result.stdout)
        self.assertIn('ether saddr AA:BB:CC:DD:EE:FF counter drop', result.stdout)

    def test_resume_removes_only_own_table(self):
        result = self.execute(hour='07')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), 'delete table inet home_child')

    def test_existing_table_is_updated_in_one_transaction(self):
        result = self.execute(exists=True)
        self.assertIn('flush chain inet home_child block', result.stdout)
        self.assertNotIn('delete table', result.stdout)

    def test_mac_injection_rejected(self):
        result = self.execute(mac='AA:BB:CC:DD:EE:FF;echo-bad')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')

    def test_interface_injection_rejected(self):
        result = self.execute(lan='br-lan";flush ruleset')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')

    def test_missing_devices_rejected(self):
        self.assertNotEqual(self.execute(mac='').returncode, 0)


@unittest.skipIf(os.name == 'nt', 'POSIX storage checks run on Linux')
class StorageGuard(unittest.TestCase):
    def execute(self, *, mounted=True, marker='unit', free_kib=50000000):
        directory = fixture()
        local, nas, tools = directory/'data', directory/'nas', directory/'tools'
        for path in (local/'appdata/transmission', nas/'incomplete', nas/'complete', tools):
            path.mkdir(parents=True)
        (nas/'.openwrt-download-target').write_text(marker)
        mounts = directory/'mounts'
        mounts.write_text(f'/dev/fake {local} ext4 rw 0 0\n' + (f'192.0.2.1:/Downloads {nas} nfs4 rw 0 0\n' if mounted else ''))
        values = {'homerouter.nas.enabled':'1', 'homerouter.nas.source':'192.0.2.1:/Downloads',
                  'homerouter.nas.marker':'unit', 'homerouter.nas.data_uuid':'1234-abcd',
                  'homerouter.nas.min_free_gib':'10', 'transmission.@transmission[0].user':'transmission',
                  'transmission.@transmission[0].download_dir':str(nas/'complete'),
                  'transmission.@transmission[0].incomplete_dir':str(nas/'incomplete'),
                  'transmission.@transmission[0].config_dir':str(local/'appdata/transmission')}
        commands = {
            'uci': '#!/usr/bin/env python3\nimport json,os,sys\nprint(json.loads(os.environ["GUARD_UCI"])[sys.argv[-1]])\n',
            'blkid': '#!/bin/sh\nprintf "1234-abcd\\n"\n',
            'df': '#!/bin/sh\nprintf "Filesystem 1024-blocks Used Available Capacity Mounted\\n"\nprintf "test 999999999 1 %s 1%% test\\n" "$GUARD_FREE"\n',
            'su': '#!/bin/sh\n[ "$1" = -s ] && [ "$2" = /bin/sh ] && [ "$3" = -c ] && [ "$5" = transmission ] || exit 2\nexec sh -c "$4"\n',
        }
        for name, content in commands.items():
            path = tools/name
            path.write_text(content)
            path.chmod(0o755)
        content = (ROOT/'packages/home-router-tools/files/usr/sbin/home-storage-check').read_text(encoding='utf-8')
        content = content.replace('/mnt/nas-downloads', str(nas)).replace('/srv/data', str(local)).replace('/proc/mounts', str(mounts)).replace('/tmp/home-storage-check.lock', str(directory/'guard.lock'))
        script = directory/'check.sh'
        script.write_text(content)
        script.chmod(0o755)
        env = dict(os.environ, PATH=str(tools)+os.pathsep+os.environ['PATH'], GUARD_UCI=json.dumps(values), GUARD_FREE=str(free_kib))
        result = subprocess.run([str(script)], env=env, text=True, capture_output=True, timeout=15)
        return result, nas

    def test_valid_mount_and_permissions_allow_start(self):
        result, nas = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((nas/'.openwrt-write-probe').exists())

    def test_unmounted_directory_never_passes_or_writes_probe(self):
        result, nas = self.execute(mounted=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((nas/'.openwrt-write-probe').exists())

    def test_wrong_share_marker_fails_closed(self):
        result, nas = self.execute(marker='different-nas')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((nas/'.openwrt-write-probe').exists())

    def test_insufficient_space_rejects_start(self):
        result, _ = self.execute(free_kib=100)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
