local sys = require "luci.sys"
local m = Map("homesmb", "网络共享挂载 · SMB/CIFS", "把群晖或其他 NAS 的共享文件夹挂到软路由。NAS 不在线时后台重试，不阻塞路由启动。用于下载时保留 /mnt/nas-downloads，并在家庭上网控制中配置共享标识、本地数据盘 UUID 和存储保护。")
local s = m:section(NamedSection, "nas", "mount", "共享设置")
s.addremove = false
local status = s:option(DummyValue, "_status", "当前状态")
status.template = "homeui/smb-status"
function status.cfgvalue() return sys.exec("/usr/sbin/home-smb status 2>/dev/null"):sub(1, 1024) end
s:option(Flag, "enabled", "启用并自动重连").rmempty = false
local server = s:option(Value, "server", "NAS 地址", "IPv4 地址或主机名，例如 192.168.1.100；不填写 smb://。")
function server.validate(self, value)
    if value and #value <= 253 and value:match("^[a-zA-Z0-9][a-zA-Z0-9.-]*$") then return value end
    return nil, "请输入有效的 NAS IPv4 地址或主机名。"
end
local share = s:option(Value, "share", "共享名", "例如 Downloads；支持中文，但不含斜杠、空格或控制字符。")
function share.validate(self, value)
    if value and #value > 0 and #value <= 255 and not value:find("[%s%c/\\]") then return value end
    return nil, "共享名不能为空，且不能含斜杠、空格或控制字符。"
end
local target = s:option(Value, "target", "本地挂载点")
target.default = "/mnt/nas-downloads"
target.rmempty = false
function target.validate(self, value)
    if value and value:match("^/mnt/[a-zA-Z0-9_-]+$") then return value end
    return nil, "挂载点须为 /mnt/ 下的单层英文目录。"
end
local guest = s:option(Flag, "guest", "访客访问", "通常保持关闭，使用群晖专用账号。")
guest.default = "0"
guest.rmempty = false
local username = s:option(Value, "username", "用户名")
username:depends({guest = "1", ["!reverse"] = true})
local password = s:option(Value, "password", "密码")
password.password = true
password:depends({guest = "1", ["!reverse"] = true})
local domain = s:option(Value, "domain", "域／工作组（可选）")
for _, option in ipairs({username, password, domain}) do
    function option.validate(self, value)
        if not value or not value:find("%c") then return value end
        return nil, "不能含换行或控制字符。"
    end
end
local version = s:option(ListValue, "version", "SMB 协议")
version:value("3.0", "SMB 3.0（兼容优先）")
version:value("3.1.1", "SMB 3.1.1")
version.default = "3.0"
local owner = s:option(ListValue, "owner", "本地访问用户")
owner:value("transmission", "Transmission 下载服务")
owner:value("root", "路由器管理员")
owner.default = "transmission"
local retry = s:option(Button, "_retry", "挂载／重试", "先保存并应用设置，再点击重试。")
retry.inputtitle = "启动或重试"
retry.inputstyle = "apply"
function retry.write() sys.call("/etc/init.d/home-smb restart >/dev/null 2>&1") end
local stop = s:option(Button, "_stop", "停止并卸载", "本次停止服务；下次开机仍按启用选项执行。下载共享卸载前会暂停 Transmission。")
stop.inputtitle = "停止并卸载"
function stop.write() sys.call("/etc/init.d/home-smb stop >/dev/null 2>&1") end
function m.on_after_commit(self)
    sys.call("chmod 0600 /etc/config/homesmb")
    if self.uci:get("homesmb", "nas", "enabled") == "1" then
        sys.call("/etc/init.d/home-smb enable >/dev/null 2>&1")
    else sys.call("/etc/init.d/home-smb disable >/dev/null 2>&1") end
end
return m
