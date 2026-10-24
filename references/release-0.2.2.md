# Tidvo 0.2.2 Beta

修复 macOS 上无法查看系统 PID 1 时，所有清理都被占用检查拦住的问题。

对明确可重建、属于当前用户的缓存，新增经校准的当前用户占用检查：验证真实
打开文件可被发现，核对当前用户进程可见性，再检查目标。打开的文件、警告、
超时或缺失进程仍会阻止清理；日志、构建产物、会话和数据库不因此放宽。

操作记录会说明检查范围，保留文件所有权、身份、配置引用、Agent 数据保护及
废纸篓检查。没有提权、修改系统权限或永久删除。详细限制见
`references/occupancy-checks.md`。

直接说“帮我清理一下电脑”即可开始。当前支持 macOS 14+ 与 Python 3.11+；
Windows 支持规划中。旧计划需重新扫描生成，配置与恢复记录继续保留。

一句话安装／更新入口：

> 帮我安装 Tidvo：https://raw.githubusercontent.com/sanzhangzui/tidvo/main/INSTALL.md

移入废纸篓通常不会立即释放空间。GPL-3.0-only，包含固定版本的 Mole 源码及
修改声明；本次没有修改 vendored Mole。
