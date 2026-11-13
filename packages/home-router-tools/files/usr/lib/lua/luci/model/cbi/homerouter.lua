local m = Map("homerouter", "家庭上网控制", "每天 00:00 起限制指定设备，按整点恢复。启用前确认时间、LAN 接口和设备 MAC；关闭流量卸载。执行周期约 15 秒，实机验收前作为候选功能。随机 MAC 或移动数据不受此固定标识规则覆盖。")
local s = m:section(NamedSection, "child", "child", "夜间控制")
local enabled = s:option(Flag, "enabled", "启用")
enabled.default = "0"
local lan = s:option(Value, "lan_device", "LAN 桥接口")
lan.datatype = "networkdevicename"
lan.default = "br-lan"
local resume = s:option(Value, "resume_hour", "早晨恢复时间（整点）")
resume.datatype = "range(1,23)"
resume.default = "7"
local mac = s:option(DynamicList, "mac", "孩子设备 MAC 地址")
mac.datatype = "macaddr"
local nas = m:section(NamedSection, "nas", "nas", "群晖下载存储保护")
nas:option(Flag, "enabled", "启用存储保护与下载监督").default = "0"
nas:option(Value, "source", "实际挂载源", "与 /proc/mounts 一致，例如 NAS_IP:/volumeX/Downloads 或 //NAS_IP/Downloads。不填密码。")
local marker = nas:option(Value, "marker", "共享标识", "在共享根目录 .openwrt-download-target 中写入相同英文标识，标识只用字母、数字、下划线和减号。")
marker.datatype = "uciname"
nas:option(Value, "data_uuid", "本地 /srv/data 的 ext4 UUID")
local minimum = nas:option(Value, "min_free_gib", "群晖最少剩余空间 GiB")
minimum.datatype = "range(1,100000)"
minimum.default = "10"
return m
