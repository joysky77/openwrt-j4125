# 云编译实施记录

日期：2026-11-13。该记录保存已发生的检查结果，后续运行状态以对应 Actions 链接和 Artifact 为准。

## 工程与可重建输入

- 公开仓库：https://github.com/joysky77/openwrt-j4125
- 固件项目版本：0.1.0-rc1，目标 x86/64。
- 原始源码、feeds、代理组件和 GitHub Actions 都固定完整提交，见 configs/build-lock.json。
- 生成 Legacy/UEFI SquashFS 完整磁盘镜像；产物检查要求启动区 256MiB、系统区 4GiB，以及完整的必需包 manifest。
- 发布前还需完成真实硬件、安装目标、NAS、DNS/代理、打印、孩子设备及 48–72 小时连续运行验证。

## 已验证结果

- Windows 项目静态检查通过；Linux 上的构建及运行逻辑测试通过。
- 最新静态回归共 25 项，覆盖配置丢失拦截、镜像 MBR/GPT 分区大小、gzip 尾部元数据处理、夜间 nft 规则和参数校验、NAS 未挂载/错误共享/空间不足时拒绝启动。
- 云端静态检查证据：https://github.com/joysky77/openwrt-j4125/actions/runs/43428516017
- 以下候选构建的运行器资源、构建依赖、配置解析及全部必需组件选择检查通过，源码下载完成并进入正式编译：https://github.com/joysky77/openwrt-j4125/actions/runs/43427357911
- 该次镜像构建使用提交 b0d0b76；其后的 c209419 只增加隔离 QEMU 验证、解压测试和说明，没有改变固件运行组件。
- 新增的 QEMU 工作流仅在成功构建后触发；本段记录时尚无 QEMU 启动通过证据。

## 已解决的构建问题

- 明确关闭 BUILDBOT 导致的无关包/内核模块扩选，保留 SDK/Image Builder。
- 只安装所选包配方及其依赖，避免无关应用的上游 Kconfig 循环依赖。
- feeds 索引阶段可能归一化并丢弃尚未安装的包选项，因此在配方安装完成后恢复 seed，再执行 defconfig 和严格检查。
- 对 PassWall2 的嵌套核心选项补充显式 Xray/sing-box 配方安装；不允许因缺核心而交付缩水镜像。
- 对照实际 LuCI 源码修正服务状态命令的 UCI 命名空间，并采用可用的接口字段校验。

早期失败/取消的诊断下载到本地 artifacts 目录，继续保留。旧配置规划文件未上传公开仓库；个人备份、密码、订阅和身份密钥均不作为公开构建输入。

## 运行边界

- NAS 启动检查和监督已实现并有模拟测试，但真实 NFS hard I/O 阻塞、权限映射、断线重连和任务恢复仍需实机验证。
- 夜间规则按固定 MAC 和入口接口运行，检查周期约 15 秒；移动数据、随机 MAC 和其他入口需单独处理。
- Docker、下载、代理、AdGuard Home 等需要配置的服务初始不启用，基础 DHCP/DNS 保持官方路径。
- 自动 QEMU 验证没有真实网卡与磁盘，不能代替实体设备和 UEFI 验证。

## 2026-11-14 后续结果

- 源码编译与镜像/manifest/分区检查成功，构建 run 43427357911 已完成。
- 初始 QEMU 工作流的 artifact 提取目录问题和测试命令格式问题已修复；固件镜像没有因此重编或改写。
- 双启动模式验证通过：https://github.com/joysky77/openwrt-j4125/actions/runs/43548717718 。Legacy 和 UEFI 都验证了正常初始化、主要工具存在、实际夜间规则生成及早晨规则移除。之前关于 UEFI 未测试的记录仅描述当时状态。
- 当前静态回归 27 项；Windows 校验下载脚本另外验证了大写 SHA256SUMS 与小写上游 sha256sums 的区分，并确认损坏文件会被拒绝。
- 两个镜像已下载、独立校验并整理到本地 releases/v0.1.0-rc1，带安装说明、构建锁与双模式启动证据。完整构建产物另保存在本地 artifacts/releases 下，后续校验结果以 workflow-run.json 为准。
- 用户确认小主机当前未运行 OpenWrt，按新安装准备，不能因此假设磁盘为空；安装前仍需确认 BIOS、网卡和目标磁盘。参见 INSTALL-PREPARATION.md。
- 实体设备、无线 WAN、打印、群晖断线恢复和长时稳定性仍待验证，候选状态不变。

## 2026-11-18 存储容量更正

用户实查磁盘为标称 120GB、内存仍为 8GB。读取本地两份候选镜像分区表，启动区均为 256MiB、系统区均为 4GiB，可继续用于该磁盘，无需修改二进制或重新编译。

剩余数据区约 107.51GiB（格式化前），目录预算调整为 Docker/应用 32GiB、rclone 缓存目标 16GiB、可选本地下载 24GiB、备份/日志 5GiB，余量约 30.51GiB，再扣除文件系统开销。群晖仍承担默认下载文件，本地低空间目标保持 30GiB 预警/20GiB 保护。

本地规划保存为 docs/定制方案-v0.5.md 和 configs/storage-plan-v0.5.json；候选版本目录新增安装说明-120GB-v1.1.md 及独立校验文件。旧规划、旧安装说明、原 SHA256SUMS 与两个镜像均保持不变。尚未对真实设备分区或应用服务配置。

## 2026-11-19 ZeroTier 网页补丁

用户已确认实机为 OpenWrt 25.12.6。交付 manifest 有 zerotier 1.16.2，但遗漏网页配置插件。新增独立包 luci-app-home-zerotier 0.1.1-r1，匹配锁定服务的 global/network UCI 格式。默认不接管默认路由/DNS，不自动修改防火墙。

在 D:\AiTemp\openwrt-cloud-tools 的独立虚拟环境运行 Lua 5.1 检查，使用交付 SDK 内置 apk-tools 3.0.5 对四个架构无关的 LuCI 文件直接打包，并完成包校验、解包比对和 root:root 文件权限检查。SDK 常规 make 的宿主依赖检查未通过（DrvFS 大小写、ncurses、unzip），未安装宿主依赖或强行执行完整构建。

安装包和带固件版本/SHA256 检查的 Windows 安装脚本保存在 releases/addons/zerotier-0.1.1。此包没有公共源签名，安装仅对该已核验文件使用 --allow-untrusted。尚未操作实机，实际 LuCI 菜单、保存应用及 ZeroTier 网络连通性仍待用户安装验证。未重建镜像、未修改历史交付包、未推送仓库。

## 2026-11-20 家庭管理界面更新 0.2.0

新增 Argon 3.1.4（含中文）、家庭服务入口、常用网络状态与设置入口、SMB/CIFS 客户端管理。保留现有 Dockerman JS 与 p910nd；纳入 ZeroTier 页面 0.1.2-r1。独立更新六个 APK 合计约 0.75MiB，安装器备份配置并重启网页服务，不修改网络参数或重写磁盘。

源码和后续整包配置在 codex/home-ui-0.2.0 分支，验证提交 c9de12fc1f6d616f246f5e67ccea9e62a0960b9a；整包下一候选配置为 0.2.0-rc1，历史 0.1.0-rc1 镜像不变。本次没有启动新的整包编译。

云端 run 44746800232 成功：原交付固件 QEMU 安装、Argon 登录、桌面与手机页面、现有插件 HTTP 200、SMB 网页保存应用、后台服务重载和密码保护均通过。此前测试发现并修复了虚拟测试介质兼容、stat 命令假设、CBI 未勾选 Flag 的依赖条件、UCI shell 严格模式及 procd 重载行为；不把安装包能生成作为业务通过的依据。

实际安装包位于 releases/addons/home-ui-0.2.0，六包下载 SHA256 和 Windows PowerShell 5.1 校验模式通过，附 validation.json 与截图。未在小主机安装，真实群晖/打印及长期稳定性仍未验收；不宣称完成了实机部署。
