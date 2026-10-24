# Tidvo 0.2.4 Beta

清理报告按“可生成计划的缓存、需退出应用后复查、需单独确认、明确保留、检查
不完整”汇总容量，展示被保留的大项及下一步。未知大小与下界单独显示；终端
使用十进制 MB/GB，长清单展示代表条目，完整内容保留在 JSON 中。

补充地图瓦片、Apple 媒体／Python／parsecd、媒体分析临时文件、Xcode Interface
Builder、Android SDK 元数据、Homebrew 下载／API、Cargo 下载、Ruby／Bundler
索引及 PyInstaller 缓存规则。保留 SDK、AVD、已安装依赖、Cargo 源码、模型、
未完成下载和锁文件。未知应用缓存仅报告归属待确认。

npm 等目标因所有权问题不能清理时，可只读测量可读取的元数据，显示容量及
缺口，不放宽删除权限。Homebrew 原生 dry-run 可单独预览，不叠加为可清理容量，
也不自动执行 Homebrew 清理。

旧 Agent 扩展程序包具备过期标记、更新注册版本、无已知持久数据和无占用／引用
等证据时可单独审查；会话、记忆、共享资源和用户声明保护仍保留。计划及执行
重新核验注册、版本、包内容和引用，详见 references/cleanup-coverage.md。

仍只按已确认计划移入废纸篓并保存恢复记录；不提权、不永久删除、不结束应用。
支持 macOS 14+／Python 3.11+；Windows 规划中。旧计划需重新生成。
