#!/usr/bin/env python3
"""Install and exercise the UI bundle in a snapshot of the delivered firmware."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from smoke_boot import decompress_image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('firmware')
    parser.add_argument('bundle')
    parser.add_argument('evidence')
    args = parser.parse_args()
    firmware, bundle, evidence = [Path(v).resolve() for v in (args.firmware, args.bundle, args.evidence)]
    evidence.mkdir(parents=True, exist_ok=True)
    image = next(firmware.glob('*squashfs-combined.img.gz'))
    raw = evidence.parent / 'ui-test-disk.img'
    decompress_image(image, raw)
    media = evidence.parent / 'ui-test-bundle.img'
    with media.open('xb') as stream:
        stream.truncate(64 * 1024 * 1024)
    subprocess.run(['mkfs.vfat', str(media)], check=True)
    subprocess.run(['mcopy', '-i', str(media), *map(str, bundle.iterdir()), '::/'], check=True)
    log = evidence / 'serial.log'
    command = ['qemu-system-x86_64', '-machine', 'pc', '-accel', 'tcg', '-cpu', 'qemu64',
               '-m', '1536', '-smp', '2', '-nographic', '-monitor', 'none', '-no-reboot', '-snapshot',
               '-drive', f'file={raw},format=raw,if=ide,index=0',
               '-drive', f'file={media},format=raw,if=ide,index=1',
               '-netdev', 'user,id=net0,restrict=on,hostfwd=tcp:127.0.0.1:18080-:80',
               '-device', 'e1000,netdev=net0']
    setup = r'''
tries=0
while [ "$(cat /proc/sys/kernel/hostname)" = '(none)' ] && [ "$tries" -lt 60 ]; do sleep 2; tries=$((tries+1)); done
tries=0
while { ! grep -q ' /overlay ' /proc/mounts || ! ip link show br-lan >/dev/null 2>&1; } && [ "$tries" -lt 60 ]; do sleep 2; tries=$((tries+1)); done
mkdir -p /mnt/ui-bundle
mount -t vfat /dev/sdb /mnt/ui-bundle || echo UI_INSTALL_FAILED:mount
cd /mnt/ui-bundle
sha256sum -c SHA256SUMS || echo UI_INSTALL_FAILED:checksum
sh /mnt/ui-bundle/install_ui_update.sh __MANIFEST_HASH__ || echo UI_INSTALL_FAILED:apk
test -f /usr/lib/lua/luci/controller/homeui.lua || echo UI_INSTALL_FAILED:controller
test "$(stat -c %a /etc/config/homesmb)" = 600 || echo UI_INSTALL_FAILED:permissions
test "$(uci -q get homesmb.nas.enabled)" = 0 || echo UI_INSTALL_FAILED:default
uci set luci.main.mediaurlbase='/luci-static/argon'
uci commit luci
printf 'home-ui-qemu-only
home-ui-qemu-only
' | passwd root
ip addr add 10.0.2.15/24 dev br-lan
/etc/init.d/rpcd restart
/etc/init.d/uhttpd restart
echo HOME_UI_READY
'''
    with log.open('wb') as output:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT)
        def send(text):
            process.stdin.write(text.encode()); process.stdin.flush()
        def wait_for(pattern, seconds=240):
            deadline = time.monotonic() + seconds
            last_enter = 0
            while time.monotonic() < deadline:
                text = log.read_text(errors='replace')
                if 'UI_INSTALL_FAILED:' in text and re.search(r'^UI_INSTALL_FAILED:', text, re.M):
                    raise RuntimeError('UI install failed; see serial log')
                if re.search(pattern, text, re.M):
                    return
                if process.poll() is not None:
                    raise RuntimeError('Guest exited unexpectedly')
                if pattern.startswith('root@') and time.monotonic() - last_enter > 10:
                    send('\n')
                    last_enter = time.monotonic()
                time.sleep(2)
            raise TimeoutError('Timed out waiting for ' + pattern)
        try:
            send('\n')
            wait_for(r'root@[^\r\n]+[#] ')
            setup = setup.replace('__MANIFEST_HASH__', hashlib.sha256((bundle / 'SHA256SUMS').read_bytes()).hexdigest())
            send(setup)
            wait_for(r'^HOME_UI_READY\s*$', 300)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                page.route('**/*', lambda route: route.continue_() if route.request.url.startswith('http://127.0.0.1:18080/') else route.abort())
                base = 'http://127.0.0.1:18080/cgi-bin/luci/'
                page.goto(base, wait_until='networkidle')
                page.locator('input[name="luci_username"]').fill('root')
                page.locator('input[name="luci_password"]').fill('home-ui-qemu-only')
                page.locator('button[type="submit"], input[type="submit"]').first.click()
                page.wait_for_timeout(3000)
                page.goto(base + 'admin/services/home-tools', wait_until='networkidle')
                page.locator('.homeui-card').first.wait_for()
                assert page.locator('.homeui-card').count() == 8
                page.wait_for_timeout(1500)
                page.screenshot(path=str(evidence / 'desktop-services.png'), full_page=True)
                page.goto(base + 'admin/network/home-settings', wait_until='networkidle')
                page.wait_for_function("document.querySelector('#homeui-interfaces').textContent.includes('LAN')")
                page.screenshot(path=str(evidence / 'desktop-network.png'), full_page=True)
                response = page.request.get(base + 'admin/services/home-tools/status')
                assert response.status == 200 and response.json()['interfaces']
                assert 'password' not in response.text().lower()
                page.goto(base + 'admin/services/home-smb', wait_until='networkidle')
                page.locator('input[type="password"]').wait_for()
                page.screenshot(path=str(evidence / 'desktop-smb.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                page.goto(base + 'admin/services/home-tools', wait_until='networkidle')
                page.locator('.homeui-card').first.wait_for()
                page.screenshot(path=str(evidence / 'mobile-services.png'), full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                # Existing plugin routes must still load with the new theme.
                for route in ['services/dockerman', 'services/p910nd', 'services/homezerotier', 'network/network']:
                    page.goto(base + 'admin/' + route, wait_until='networkidle')
                    assert page.locator('body').inner_text().find('404 Not Found') < 0, route
                browser.close()
            backend = r'''
uci set homesmb.nas.enabled=1
uci set homesmb.nas.server=192.0.2.10
uci set homesmb.nas.share='测试下载'
uci set homesmb.nas.username=test-user
uci set homesmb.nas.password='QEMU-test,secret=$(false)'
uci set homesmb.nas.target=/mnt/ui-test
uci set homesmb.nas.owner=root
uci commit homesmb
if [ -e /usr/sbin/mount.cifs ]; then mv /usr/sbin/mount.cifs /usr/sbin/mount.cifs.pre-ui-test; fi
printf '#!/bin/sh\nprintf "%%s\\n" "$@" > /tmp/ui-mount-arguments\nexit 1\n' > /usr/sbin/mount.cifs
chmod 755 /usr/sbin/mount.cifs
errors=0
home-smb mount && errors=$((errors+1))
test "$(stat -c %a /etc/home-smb/credentials)" = 600 || errors=$((errors+1))
test "$(stat -c %a /mnt/ui-test)" = 700 || errors=$((errors+1))
grep -q 'password=QEMU-test,secret=$(false)' /etc/home-smb/credentials || errors=$((errors+1))
if grep -q QEMU-test /tmp/ui-mount-arguments; then errors=$((errors+1)); fi
uci set homesmb.nas.target=/etc
home-smb mount && errors=$((errors+1))
echo HOME_UI_BACKEND_RESULT:$errors
'''
            send(backend)
            wait_for(r'^HOME_UI_BACKEND_RESULT:0\s*$', 60)
            (evidence / 'validation.json').write_text(json.dumps({
                'baseline_openwrt': '25.12.6', 'apk_install': True, 'argon_login': True,
                'desktop_pages': True, 'mobile_layout': True, 'existing_plugin_routes': True,
                'smb_credential_permissions': True, 'smb_no_password_in_argv': True,
                'smb_invalid_target_rejected': True, 'real_nas_mount': False,
                'physical_router_tested': False}, indent=2) + '\n')
        finally:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)


if __name__ == '__main__':
    main()
