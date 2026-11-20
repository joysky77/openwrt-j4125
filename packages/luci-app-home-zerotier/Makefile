include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-home-zerotier
PKG_VERSION:=0.1.2
PKG_RELEASE:=1
PKG_LICENSE:=MIT
PKGARCH:=all

include $(INCLUDE_DIR)/package.mk

define Package/luci-app-home-zerotier
  SECTION:=luci
  CATEGORY:=LuCI
  TITLE:=ZeroTier client configuration for the home router
  DEPENDS:=+zerotier +luci-base +luci-compat
endef

define Build/Compile
endef

define Package/luci-app-home-zerotier/install
	$(CP) ./files/* $(1)/
endef

$(eval $(call BuildPackage,luci-app-home-zerotier))
