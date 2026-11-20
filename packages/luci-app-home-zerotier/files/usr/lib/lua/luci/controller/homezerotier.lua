module("luci.controller.homezerotier", package.seeall)
local fs = require "nixio.fs"

function index()
    if not fs.access("/etc/config/zerotier") then return end
    local page = entry({"admin", "services", "homezerotier"}, cbi("homezerotier"), _("ZeroTier"), 65)
    page.dependent = true
    page.acl_depends = {"luci-app-home-zerotier"}
end
