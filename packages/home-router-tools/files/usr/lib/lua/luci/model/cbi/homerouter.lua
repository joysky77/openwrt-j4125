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
return m
