module("luci.controller.homeui", package.seeall)
local fs = require "nixio.fs"

function index()
    entry({"admin", "services", "home-tools"}, template("homeui/index"), _("家庭服务"), 1)
    entry({"admin", "network", "home-settings"}, template("homeui/network"), _("常用设置"), 1)
    local smb = entry({"admin", "services", "home-smb"}, cbi("homesmb"), _("网络共享挂载"), 66)
    smb.acl_depends = {"luci-app-home-ui"}
    local status = entry({"admin", "services", "home-tools", "status"}, call("status_json"))
    status.leaf = true
end

function status_json()
    local util = require "luci.util"
    local http = require "luci.http"
    local sys = require "luci.sys"
    local result = {interfaces = {}, ports = {}, printers = {}, services = {}}
    local dump = util.ubus("network.interface", "dump", {}) or {}
    for _, item in ipairs(dump.interface or {}) do
        local addresses = {}
        for _, addr in ipairs(item["ipv4-address"] or {}) do
            addresses[#addresses + 1] = tostring(addr.address or "") .. "/" .. tostring(addr.mask or "")
        end
        local dev = tostring(item.l3_device or item.device or "")
        local mac, speed, carrier = "", "", ""
        if dev:match("^[a-zA-Z0-9_.:-]+$") then
            mac = (fs.readfile("/sys/class/net/" .. dev .. "/address") or ""):gsub("%s+$", "")
            speed = (fs.readfile("/sys/class/net/" .. dev .. "/speed") or ""):gsub("%s+$", "")
            carrier = (fs.readfile("/sys/class/net/" .. dev .. "/carrier") or ""):gsub("%s+$", "")
        end
        result.interfaces[#result.interfaces + 1] = {
            name = tostring(item.interface or ""), up = item.up == true,
            device = dev, ipv4 = addresses, mac = mac, speed = tonumber(speed), carrier = tonumber(carrier)
        }
    end
    for name in fs.dir("/sys/class/net") do
        if name:match("^[a-zA-Z0-9_.:-]+$") and fs.access("/sys/class/net/" .. name .. "/device") then
            local prefix = "/sys/class/net/" .. name
            result.ports[#result.ports + 1] = {
                name = name,
                mac = (fs.readfile(prefix .. "/address") or ""):gsub("%s+$", ""),
                carrier = tonumber(fs.readfile(prefix .. "/carrier") or ""),
                speed = tonumber(fs.readfile(prefix .. "/speed") or "")
            }
        end
    end
    for _, name in ipairs({"dockerd", "zerotier", "p910nd", "transmission", "home-smb"}) do
        local service = util.ubus("service", "list", {name = name}) or {}
        local running = false
        for _, instance in pairs((service[name] or {}).instances or {}) do
            if instance.running then running = true end
        end
        result.services[name] = running
    end
    if fs.access("/dev/usb") then
        for name in fs.dir("/dev/usb") do
            if name:match("^lp%d+$") then result.printers[#result.printers + 1] = "/dev/usb/" .. name end
        end
    end
    result.smb_status = sys.exec("/usr/sbin/home-smb status 2>/dev/null"):sub(1, 1024)
    -- Do not return UCI objects, passwords, PPP credentials, or Docker tokens.
    http.prepare_content("application/json")
    http.write_json(result)
end
