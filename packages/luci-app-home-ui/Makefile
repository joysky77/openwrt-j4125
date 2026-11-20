include $(TOPDIR)/rules.mk
PKG_NAME:=luci-app-home-ui
PKG_VERSION:=0.2.0
PKG_RELEASE:=1
PKG_LICENSE:=MIT
PKGARCH:=all
include $(INCLUDE_DIR)/package.mk
define Package/luci-app-home-ui
  SECTION:=luci
  CATEGORY:=LuCI
  TITLE:=Home router interface and SMB client management
  DEPENDS:=+luci-base +luci-compat +cifsmount +kmod-fs-cifs +flock +coreutils-timeout
endef
define Package/luci-app-home-ui/conffiles
/etc/config/homesmb
endef
define Build/Compile
endef
define Package/luci-app-home-ui/install
	$(CP) ./files/* $(1)/
	chmod 0755 $(1)/usr/sbin/home-smb $(1)/etc/init.d/home-smb
	chmod 0600 $(1)/etc/config/homesmb
endef
$(eval $(call BuildPackage,luci-app-home-ui))
