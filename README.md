# J4125 家用 OpenWrt 云编译

本项目为 x86/64 家用软路由构建候选固件。稳定优先，保留中文软件包管理和后续扩展能力。

**候选版本：0.1.0-rc1。编译成功不代表已通过硬件、断线恢复或长期稳定性验收。**

## 已纳入功能

- 中文 LuCI、软件管理、网页终端、挂载管理、服务状态及网络诊断。
- Docker/Compose、ZeroTier、DDNS、UPnP、USB 打印、网络唤醒。
- Transmission 下载和做种，预留群晖 NFS/SMB 客户端支持。
- rclone/FUSE 远程 WebDAV、RTL8814AU USB 无线 WAN。
- PassWall2，Xray / sing-box，nftables 透明代理依赖。
- AdGuard Home、LibreSpeed 网页测速和 iperf3。
- 每天 00:00 起按 MAC 限制设备，恢复整点可配置；默认不启用，先确认设备和时间。

硬件网卡型号尚待确认，因此包含常见 Intel/Realtek 网卡驱动；未识别的网卡仍需补充驱动。包含 UEFI 和 Legacy 两种完整镜像。打印机型号未确认，首版提供 p910nd 与 USB 打印基础支持，不保证扫描或所有打印机兼容。

## 一键云编译

1. 在 GitHub 的 **Actions → Build candidate firmware → Run workflow** 手动启动。
2. 工作流先检查锁定提交、必需配置和运行器空间，再完整编译；不会自动定时追踪主分支。
3. 成功后下载 `firmware-candidate-*`；同时下载 `expansion-kit-*` 和 `diagnostics-*`，并保存在自己的磁盘或 NAS。
4. 在解压目录执行 `sha256sum -c SHA256SUMS` 检查完整性。固件文件名含本项目版本；原始固件版本和实际包清单保存在 metadata 中。

Artifacts 有保留期限：固件 30 天、扩展包和日志 14 天；到期前自行保存，不将其当作永久发布。默认不自动发布 GitHub Release、不自动刷机。

Windows 可以使用 `scripts/download-artifacts.ps1 -RunId <运行编号>` 一次下载该次成功构建的全部产物并校验 SHA256；每次生成独立目录，保留旧文件。

公开仓库不保存旧路由备份、账号、密钥、代理订阅或 NAS 凭据。个人配置只能在安装后导入，并按版本和接口映射适配。

## 首次安装与配置

完整磁盘镜像会改写目标盘分区；必须先确认目标盘、现有数据备份和 BIOS 启动方式。**不要将镜像直接写入含重要资料的磁盘，也不要直接恢复另一台设备的完整配置。**

- 启动区 256MiB，系统区 4GiB；500GB 盘剩余数据区按实际设备建立，UUID 挂载 `/srv/data`。
- 镜像不在首次启动自动格式化或扩容，不预设 `/dev/sda`，不假设所有网口顺序相同。
- 初始网络沿用官方 x86 默认生成逻辑，先脱离生产网络，用显示器/键盘核对 LAN 地址、网口并设置管理密码。
- 系统 → 挂载点管理本地及网络存储；系统 → 自定义命令 → 家庭路由状态查看只读状态；系统 → 启动项查看服务进程状态。
- 配置 NFS/SMB 挂载和读写权限前不启用下载，下载配置已指向 `/mnt/nas-downloads/{incomplete,complete}`。
- 默认不启用 Docker、下载器、代理、AdGuard Home、ZeroTier、UPnP、打印服务及网页终端；这是候选固件的待配置状态。先配置本地存储、访问范围和各服务，再手动启用。
- AdGuard Home 启用前须明确 DHCP、dnsmasq、代理和 DNS 上游关系，验证端口冲突与故障恢复；首次启动不改动基础 DNS 为未配置的过滤服务。
- 群晖下载启动检查与监督逻辑已加入：核对挂载源、共享标识、本地 UUID、写权限和空间；需按实际设备配置并进行断线恢复测试。磁盘初始化、旧配置迁移、WebDAV 凭据和 DNS 最终拓扑仍需基于真实环境实施。

参阅 [安装与验收](docs/INSTALL.md) 和 [构建维护](docs/BUILD.md)。

## 扩展与稳定性

普通插件通过当前发行版软件管理器安装。驱动必须匹配内核 ABI；自编译内核不能保证兼容任意官方在线 kmod。匹配包、SDK 和 Image Builder 随成功构建归档，需要新的驱动时可用同一锁重建；不是保证任意未来插件无需重编。

不批量自动更新系统包、代理内核或容器镜像；安全更新需要及时评估、重建并验收。升级前保留可用旧版和数据备份。AI 功能尚未选择，不安装 AI Agent 或本地模型。

## 本地检查

Python 脚本仅使用标准库：

```sh
python3 scripts/project.py validate
python3 -m unittest discover -s tests -v
```

完整构建需要 Linux 区分大小写的文件系统，以及足够磁盘和内存。Windows/SMB 目录只用于编辑、静态检查和保存产物，不直接编译 OpenWrt。

源码见 `configs/build-lock.json` 中的固定提交。项目原创代码采用 MIT，OpenWrt、内核、LuCI 和各软件保留各自许可证。
