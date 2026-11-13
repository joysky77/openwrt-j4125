include $(TOPDIR)/rules.mk

PKG_NAME:=home-router-tools
PKG_VERSION:=0.1.0
PKG_RELEASE:=1
PKG_LICENSE:=MIT
PKGARCH:=all

include $(INCLUDE_DIR)/package.mk

define Package/home-router-tools
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Conservative home router management helpers
  DEPENDS:=+luci-base +luci-compat +luci-lib-jsonc +nftables-json +coreutils-timeout +flock +blkid +luci-app-commands
endef

define Package/home-router-tools/conffiles
/etc/config/homerouter
endef

define Build/Compile
endef

define Package/home-router-tools/install
	$(CP) ./files/* $(1)/
	chmod 0755 $(1)/usr/sbin/home-router-status $(1)/usr/sbin/home-child-policy $(1)/etc/init.d/home-child-policy $(1)/etc/uci-defaults/90-home-router
	chmod 0755 $(1)/usr/sbin/home-storage-check $(1)/usr/sbin/home-nas-watch $(1)/etc/init.d/home-nas-watch
endef

$(eval $(call BuildPackage,home-router-tools))
