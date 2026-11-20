local sys = require "luci.sys"
local m = Map("zerotier", "ZeroTier", "加入你自己的 ZeroTier 网络。请把示例 Network ID 替换为实际的 16 位网络 ID，并在 ZeroTier Central 中授权本设备。此页面不会自动修改防火墙或放通局域网。")

local s = m:section(NamedSection, "global", "zerotier", "全局设置")
s.addremove = false

local status = s:option(DummyValue, "_status", "服务状态")
function status.cfgvalue()
    if sys.call("/etc/init.d/zerotier status >/dev/null 2>&1") == 0 then
        return "运行中"
    end
    return "未运行"
end

local info = s:option(DummyValue, "_info", "节点信息")
function info.cfgvalue()
    local value = sys.exec("zerotier-cli info 2>/dev/null")
    return value ~= "" and value:gsub("[\r\n]+", " "):sub(1, 512) or "启动服务后显示节点 ID；请到控制台授权。"
end

local enabled = s:option(Flag, "enabled", "启用 ZeroTier")
enabled.rmempty = false
enabled.default = "0"

local port = s:option(Value, "port", "监听端口", "留空使用服务默认端口；0 表示随机端口。")
port.datatype = "range(0,65535)"
port.rmempty = true

local n = m:section(TypedSection, "network", "加入的网络")
n.anonymous = true
n.addremove = true

local id = n:option(Value, "id", "Network ID", "填写你自己的 16 位十六进制网络 ID。删除不使用的示例网络。")
id.rmempty = false
function id.validate(self, value)
    if value and #value == 16 and value:match("^[0-9a-fA-F]+$") then
        return value:lower()
    end
    return nil, "Network ID 必须是 16 位十六进制字符。"
end

local managed = n:option(Flag, "allow_managed", "允许分配内网 IP 和路由")
managed.default = "1"
managed.rmempty = false

local global = n:option(Flag, "allow_global", "允许公网 IP 和路由")
global.default = "0"
global.rmempty = false

local route = n:option(Flag, "allow_default", "允许接管默认路由", "家庭有线 WAN 主用时，通常保持关闭。")
route.default = "0"
route.rmempty = false

local dns = n:option(Flag, "allow_dns", "允许设置 DNS", "与本机 DNS 和代理配置共同规划后再启用。")
dns.default = "0"
dns.rmempty = false

-- LuCI applies UCI changes through its normal apply/rollback path.
-- A fixed service command avoids interpolating any user-provided values.
-- The existing procd reload trigger handles Save & Apply; startup enablement
-- follows the committed global setting. Installation itself does not run it.
function m.on_after_commit(self)
    if self.uci:get("zerotier", "global", "enabled") == "1" then
        sys.call("/etc/init.d/zerotier enable >/dev/null 2>&1")
    else
        sys.call("/etc/init.d/zerotier disable >/dev/null 2>&1")
    end
end

return m
