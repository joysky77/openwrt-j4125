import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'packages/luci-app-home-ui/files/usr/sbin/home-smb'


@unittest.skipUnless(os.name == 'posix', 'Runs the actual POSIX-shell validator on Linux')
class SMBValidation(unittest.TestCase):
    def valid(self, **changes):
        script = HELPER.read_text(encoding='utf-8')
        validator = script[script.index('valid() {'):script.index('\nmounted_source()')]
        settings = dict(server='192.168.1.100', share='下载共享', target='/mnt/nas-downloads',
                        version='3.0', owner='transmission', guest='0', username='nas-user',
                        password='literal,$(false)=value', domain='')
        settings.update(changes)
        env = dict(os.environ, **settings)
        return subprocess.run(['/bin/sh', '-c', validator + '\nvalid'], env=env).returncode == 0

    def test_unicode_share_and_literal_password(self):
        self.assertTrue(self.valid())

    def test_reject_system_mountpoints_and_traversal(self):
        for target in ['/etc', '/mnt/../etc', '/mnt/', '/mnt/a/b', '/mnt/a b']:
            with self.subTest(target=target): self.assertFalse(self.valid(target=target))

    def test_reject_shell_fragments_in_server(self):
        for server in ['nas;reboot', '$(false)', '-o', 'nas\nname']:
            with self.subTest(server=server): self.assertFalse(self.valid(server=server))

    def test_reject_credential_newline(self):
        self.assertFalse(self.valid(password='a\nusername=other'))
        self.assertFalse(self.valid(username='a\r'))

    def test_protocol_and_owner_allowlist(self):
        self.assertFalse(self.valid(version='1.0'))
        self.assertFalse(self.valid(owner='nobody'))
        self.assertTrue(self.valid(owner='root', version='3.1.1'))

    def test_guest_does_not_require_username(self):
        self.assertTrue(self.valid(guest='1', username=''))
        self.assertFalse(self.valid(guest='0', username=''))


class UpdateLock(unittest.TestCase):
    def test_downloads_use_release_urls_and_pinned_digests(self):
        lock = json.loads((ROOT / 'configs/ui-addon-lock.json').read_text())
        names = set()
        for package in lock['packages']:
            self.assertNotIn(package['name'], names)
            names.add(package['name'])
            self.assertRegex(package['sha256'], r'^[0-9a-f]{64}$')
            self.assertTrue(package['url'].startswith('https://'))
            self.assertNotIn('/master/', package['url'])
        self.assertEqual(len(names), 4)


if __name__ == '__main__':
    unittest.main()
