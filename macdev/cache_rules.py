"""Exact regenerable user-cache locations, never installed environments."""
import re

# (rule, path below Home, owner, process/package aliases, rebuild impact)
CACHE_LOCATIONS = (
    ("system.geo_tiles", "Library/Caches/GeoServices/Resources", "Maps", (), "地图瓦片会按需重新下载"),
    ("system.geo_metadata", "Library/Caches/GeoServices/ActiveTileGroup.pbd", "Maps", (), "地图资源索引会重建"),
    ("system.geo_metadata", "Library/Caches/GeoServices/ResourceManifest.pbd", "Maps", (), "地图资源索引会重建"),
    ("system.geo_metadata", "Library/Caches/GeoServices/SearchAttribution.pbd", "Maps", (), "地图资源索引会重建"),
    ("system.media_temp", "Library/Containers/com.apple.mediaanalysisd/Data/tmp/Pissarro", "", (), "媒体分析临时结果会重建"),
    ("system.media_temp", "Library/Containers/com.apple.mediaanalysisd/Data/tmp/TemporaryItems", "", (), "媒体分析临时结果会重建"),
    ("system.apple_python", "Library/Caches/com.apple.python/Library", "", (), "Python 编译缓存会重建"),
    ("system.apple_python", "Library/Caches/com.apple.python/Users", "", (), "Python 编译缓存会重建"),
    ("developer.xcode_ib", "Library/Developer/Xcode/UserData/IB Support/Simulator Devices", "Xcode", ("ibtool", "ibtoold", "xcodebuild", "Simulator"), "Interface Builder 预览缓存会重建；不包含模拟器设备或归档"),
    ("developer.android_metadata", ".android/cache", "", ("sdkmanager", "avdmanager"), "Android SDK 下载目录索引会重新获取；不包含 SDK 或 AVD"),
    ("developer.gem_specs", ".gem/specs", "", ("gem", "bundle", "bundler"), "Ruby gem 规格索引会重新下载；已安装 gems 保留"),
    ("developer.bundler_index", ".bundle/cache/compact_index", "", ("bundle", "bundler"), "Bundler 索引会重新下载；安装环境与 Git 源码缓存保留"),
)

MEDIA_CHILDREN = ("DynamicUI", "Engagement", "Metrics", "PaymentSheetsUI", "Storage", "fsCachedData")
PARSECD_CHILDREN = ("CustomFeedback", "bag.plist", "installed_app_whitelist_url")
REGENERABLE_RULES = frozenset(rule for rule, *_ in CACHE_LOCATIONS) | {
    "system.apple_media", "system.parsecd", "developer.homebrew_cache",
    "developer.cargo_download", "developer.pyinstaller"}


def discover_cache_rules(scanner):
    home = scanner.home
    for rule, relative, owner, packages, impact in CACHE_LOCATIONS:
        scanner.add(home / relative, rule, "system_caches" if rule.startswith("system.") else "package_managers",
                    owner=owner, packages=packages, notes=["known_regenerable_cache", impact])
    for child in MEDIA_CHILDREN:
        scanner.add(home / "Library/Caches/com.apple.AppleMediaServices" / child,
                    "system.apple_media", "system_caches", notes=["known_regenerable_cache", "Apple 媒体服务页面及资源缓存会重建"])
    for child in PARSECD_CHILDREN:
        scanner.add(home / "Library/Caches/com.apple.parsecd" / child,
                    "system.parsecd", "system_caches", notes=["known_regenerable_cache", "系统搜索资源索引会重建"])
    for child in scanner.children(home / "Library/Caches/Homebrew"):
        # Homebrew downloads/API metadata only; not Cellar, Caskroom or installed tools.
        if child.name == "downloads" and child.is_dir() and not child.is_symlink():
            for archive in scanner.children(child):
                known = (archive.is_file() and not archive.is_symlink()
                         and bool(re.fullmatch(r"[a-fA-F0-9]{32,64}--.+", archive.name))
                         and not archive.name.endswith((".incomplete", ".lock")))
                scanner.add(archive, "developer.homebrew_cache", "package_managers", packages=["brew"], report_only=not known,
                            notes=["known_regenerable_cache" if known else "unrecognized_download_entry", "Homebrew 下载缓存；未完成下载和锁文件保留"])
        elif child.name == "api" or child.is_file() and child.name.endswith((".tar.gz", ".zip", ".json")):
            scanner.add(child, "developer.homebrew_cache", "package_managers", packages=["brew"],
                        notes=["known_regenerable_cache", "Homebrew 下载和 API 缓存；后续可能重新下载"])
    for registry in scanner.children(home / ".cargo/registry/cache"):
        if registry.is_dir() and not registry.is_symlink():
            for archive in scanner.children(registry):
                scanner.add(archive, "developer.cargo_download", "package_managers", packages=["cargo"],
                            report_only=not archive.is_file() or archive.is_symlink() or archive.suffix != ".crate",
                            notes=["known_regenerable_cache", "Cargo crate 下载包；保留 registry/src、索引和安装工具"])
    for cache in scanner.children(home / "Library/Application Support/pyinstaller"):
        if cache.name.startswith("bincache"):
            scanner.add(cache, "developer.pyinstaller", "package_managers", packages=["pyinstaller"],
                        notes=["known_regenerable_cache", "PyInstaller 二进制处理缓存会在下次打包时重建"])
