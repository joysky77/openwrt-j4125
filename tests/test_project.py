import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('project', ROOT / 'scripts/project.py')
project = importlib.util.module_from_spec(spec)
spec.loader.exec_module(project)


def fixture():
    # Preserve generated fixtures instead of deleting files on the user's host.
    directory = ROOT / 'artifacts/test-fixtures' / uuid.uuid4().hex
    directory.mkdir(parents=True)
    return directory


class BuildChecks(unittest.TestCase):
    def test_lock_is_immutable(self):
        with contextlib.redirect_stdout(io.StringIO()):
            project.validate()

    def test_missing_required_package_is_a_failure(self):
        with self.assertRaisesRegex(ValueError, 'Required selections absent'):
            project.check_config(ROOT / 'README.md')

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


if __name__ == '__main__':
    unittest.main()
