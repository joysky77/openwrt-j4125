#!/usr/bin/env python3
"""Boot a candidate in isolated QEMU; no physical disks or network attached."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zlib


def decompress_image(source, target, minimum_size=(256 + 4096) * 1024**2):
    decoder = zlib.decompressobj(31)
    with source.open('rb') as compressed, target.open('wb') as raw:
        while not decoder.eof:
            chunk = compressed.read(1024 * 1024)
            if not chunk:
                raise ValueError('Truncated gzip firmware')
            # Output chunks are limited so zero padding cannot inflate RAM.
            while chunk and not decoder.eof:
                raw.write(decoder.decompress(chunk, 4 * 1024 * 1024))
                chunk = decoder.unconsumed_tail
        raw.write(decoder.flush())
    # OpenWrt appends fwtool metadata outside the gzip stream. The decompressor
    # verifies the gzip checksum and intentionally stops at the first EOF.
    if target.stat().st_size < minimum_size:
        raise ValueError('Unexpectedly short uncompressed combined image')


def main():
    source, evidence = map(lambda v: Path(v).resolve(), sys.argv[1:3])
    mode = sys.argv[3] if len(sys.argv) > 3 else 'legacy'
    if mode not in ('legacy', 'uefi'):
        raise ValueError('Unsupported boot mode')
    evidence.mkdir(parents=True, exist_ok=True)
    pattern = '*squashfs-combined-efi.img.gz' if mode == 'uefi' else '*squashfs-combined.img.gz'
    images = list(source.glob(pattern))
    if len(images) != 1:
        raise ValueError(f'Expected one {mode} candidate image')
    scratch = source.parent / 'smoke-work'
    scratch.mkdir(exist_ok=True)
    raw = scratch / f'boot-test-disk-{mode}.img'
    decompress_image(images[0], raw)
    log = evidence / 'serial.log'
    command = ['qemu-system-x86_64', '-machine', 'pc', '-accel', 'tcg',
               '-cpu', 'qemu64', '-m', '1024', '-smp', '2', '-nographic',
               '-monitor', 'none', '-no-reboot', '-snapshot', '-nic', 'none',
               '-drive', f'file={raw},format=raw,if=ide']
    if mode == 'uefi':
        code = Path('/usr/share/OVMF/OVMF_CODE_4M.fd')
        template = Path('/usr/share/OVMF/OVMF_VARS_4M.fd')
        if not code.is_file() or not template.is_file():
            raise FileNotFoundError('Standard non-secure-boot OVMF firmware missing')
        variables = scratch/'OVMF_VARS_4M.fd'
        shutil.copyfile(template, variables)
        command.extend(['-drive', f'if=pflash,format=raw,readonly=on,file={code}',
                        '-drive', f'if=pflash,format=raw,file={variables}'])
    # The raw scratch disk stays outside the logs artifact even on failure.
    check = '''
errors=0
echo HOME_SMOKE_BEGIN
tries=0
while [ "$(cat /proc/sys/kernel/hostname)" = '(none)' ] && [ "$tries" -lt 60 ]; do
  sleep 2
  tries=$((tries+1))
done
test "$(cat /proc/sys/kernel/hostname)" != '(none)' || errors=$((errors+1))
test "$(uci -q get luci.home_status.command)" = /usr/sbin/home-router-status || errors=$((errors+1))
for binary in apk uci nft docker dockerd zerotier-cli rclone transmission-daemon xray sing-box librespeed-cli home-storage-check home-child-policy; do
  command -v "$binary" || errors=$((errors+1))
done
ubus call system board || errors=$((errors+1))
uci set homerouter.child.enabled='1'
uci set homerouter.child.lan_device='br-lan'
uci set homerouter.child.resume_hour='7'
uci set homerouter.child.mac='02:00:00:00:00:01'
date -s '2026-01-01 00:01:00' || errors=$((errors+1))
home-child-policy apply || errors=$((errors+1))
nft list table inet home_child || errors=$((errors+1))
date -s '2026-01-01 07:01:00' || errors=$((errors+1))
home-child-policy apply || errors=$((errors+1))
if nft list table inet home_child 2>/dev/null; then errors=$((errors+1)); fi
echo HOME_SMOKE_RESULT:$errors
sync
poweroff
'''
    sent, result = False, None
    with log.open('wb') as output:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 360
            last_enter = 0
            while time.monotonic() < deadline:
                text = log.read_text(encoding='utf-8', errors='replace')
                if 'Kernel panic' in text:
                    raise RuntimeError('Kernel panic in emulated boot')
                if not sent and re.search(r'root@[^\r\n]+[#] ', text):
                    process.stdin.write(check.encode())
                    process.stdin.flush()
                    sent = True
                elif not sent and time.monotonic() - last_enter > 10 and process.poll() is None:
                    process.stdin.write(b'\n')
                    process.stdin.flush()
                    last_enter = time.monotonic()
                match = re.search(r'^HOME_SMOKE_RESULT:(\d+)\s*$', text, re.M)
                if match:
                    result = int(match.group(1))
                if process.poll() is not None:
                    break
                time.sleep(2)
            if process.poll() is None:
                raise TimeoutError('QEMU boot/console checks exceeded 360 seconds')
            if result != 0:
                raise RuntimeError(f'Emulated boot checks failed; result={result}')
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
    (evidence / 'boot-result.json').write_text(json.dumps({
        'boot_mode': mode, 'qemu_boot_passed': True, 'tool_checks_passed': True,
        'nft_rule_syntax_checked_in_guest': True, 'night_and_morning_policy_passed': True,
        'physical_hardware_tested': False, 'nas_disconnect_tested': False,
        'stability_soak_passed': False}, indent=2) + '\n', encoding='utf-8')
    print(f'QEMU {mode} boot and policy checks passed; physical validation remains pending.')


if __name__ == '__main__':
    main()
