module("luci.controller.homerouter", package.seeall)
function index()
    entry({"admin", "services", "homerouter"}, cbi("homerouter"), _("家庭上网控制"), 90)
end
