"""Human-readable reports; saved scans and explicit --json remain machine-readable."""
import shlex
import sys
from collections import Counter
from pathlib import Path


def safe(value):
    # Filesystem names and refusal notes must not inject terminal control codes
    # or spoof the next-step instructions with embedded newlines.
    return "".join(f"\\x{ord(c):02x}" if ord(c) < 32 or 127 <= ord(c) <= 159 else c for c in str(value))


def size(value):
    if value is None:
        return "未知"
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if abs(value) < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024


def command(*args):
    script = Path(__file__).resolve().parent.parent / "scripts/tidvo.py"
    return safe(shlex.join([sys.executable, str(script), *map(str, args)]))


def reasons(item):
    notes = item.get("evidence", [])
    values = []
    if "project_dependency_environment_preserved" in notes:
        values.append("项目依赖/虚拟环境，保留开发环境")
    if "git_tracked_or_index_unavailable" in notes:
        values.append("受 Git 跟踪或无法确认 Git 状态")
    if "nested_repository_or_sensitive_file" in notes:
        values.append("包含嵌套仓库、证书或其他敏感文件")
    if "artifact_type_not_confirmed_by_project" in notes:
        values.append("尚未确认是可重建产物")
    if "agent_data_protected" in notes:
        values.append("Agent 数据保护：会话、记忆、配置、工作区或安装资源")
    if "agent_protection_configuration_incomplete" in notes:
        values.append("Agent 保护配置未能确认，暂缓清理")
    impacts = {
        "editor_diagnostic_logs": "历史排错日志；移除后无法回看这些记录",
        "versioned_editor_compiled_cache": "编辑器编译缓存；下次启动重新生成",
        "extension_webview_resources": "扩展 Webview 页面缓存；离线资源可能需要重新下载",
        "downloaded_native_module_archive": "npm 原生模块下载包；下次安装可能重新下载",
        "downloaded_browser_component_archive": "浏览器组件下载缓存；可能需要重新下载",
        "service_worker_resources": "站点资源缓存；下次打开或离线使用可能受影响",
        "cache_origin_unverified": "站点来源未能可靠确认，保留",
        "cache_index_unavailable": "缓存索引未能安全读取，保留",
        "unrecognized_cache_layout": "目录结构尚未确认，保留",
        "unrecognized_prebuild_entry": "未确认是 npm 预编译下载包，保留",
    }
    values += [label for tag, label in impacts.items() if tag in notes]
    activity = item.get("activity", {})
    if activity.get("activity") == "active":
        values.append("有关进程仍在运行")
    elif activity.get("activity") == "unknown":
        values.append("进程状态未能确认")
    if activity.get("configured_reference"):
        values.append("仍被配置引用")
    if item.get("packages") and activity.get("reference_scan_status") != "complete":
        values.append("配置引用检查不完整")
    if item.get("scan_status") == "unavailable":
        values.append("未能完整检查：" + ", ".join(notes))
    return safe("；".join(values) or ("可选清理，执行前仍会重新检查" if item.get("action") == "trash" else ", ".join(notes)))


def candidates(items):
    lines = ["候选 ID                  状态       估算占用   路径"]
    for item in items:
        label = "待选择" if item["action"] == "trash" else "保留"
        lines.append(f"{item['id']}  {label}  {size(item.get('allocated_bytes')):>10}  {safe(item['path'])}")
        lines.append("    " + reasons(item))
    if not items:
        lines.append("未发现候选。")
    return lines


def render(kind, result, *, report_path=None):
    if kind == "agents":
        if "entries" in result:
            lines = [f"Agent 适配目录：{len(result['entries'])} 项 Agent 与相关工具", "能力范围：只读识别与数据保护；不代表全部版本或清理能力已验证。"]
            for item in result["entries"]:
                label = "已核对核心文档" if item["layout_evidence"] == "documented_defaults" else "保守位置线索，待本机核验"
                lines.append(f"{item['name']}  [{item['kind']}]  {label}")
            lines.append("下一步：通过对话请求 Agent 只读体检，查看本机实际发现的工具与数据。")
            return "\n".join(lines)
        labels = {"credentials": "凭证", "databases": "数据库及关联文件", "memory": "长期记忆", "sessions_and_tasks": "会话与任务",
                  "checkpoints": "恢复检查点", "workspaces": "工作区", "browser_state": "浏览器状态", "installed_resources": "已安装资源",
                  "diagnostics": "诊断记录", "cache_like_requires_review": "疑似缓存（仅报告）", "configuration": "配置", "unclassified_protected": "未分类保护数据"}
        lines = ["Agent 只读体检", f"登记 {result['catalog_entries']} 项 Agent 与相关工具；本次发现 {len(result['detected_tools'])} 类本地数据或应用。",
                 f"状态：{result['scan_status']}；去重后的已测占用：{size(result['total_unique_allocated_bytes'])}",
                 "以下均为仅报告。名称线索不等于已安装或完成适配；未观测到进程也不代表没有后台任务。", ""]
        for item in result["detected_tools"]:
            lines.append(f"{safe(item['name'])}  [{item['layout_evidence']}]  进程：{item['activity']}")
            for root in item["roots"]:
                partial = "（不完整，下限值）" if root.get("bytes_are_lower_bound") else ""
                lines.append(f"  {safe(root['path'])}  {size(root.get('allocated_bytes'))}{partial}  [{root['scan_status']}]")
                if root.get("via_symlink"):
                    lines.append("    共享链接目标：" + safe(root["resolved_path"]))
                lines.append("    " + "；".join(f"{labels.get(key, key)} {size(value)}" for key, value in root.get("categories", {}).items() if value))
            for app in item["app_bundles"]:
                lines.append(f"  应用版本：{safe(app['version'])}  {safe(app['path'])}")
        for issue in result["issues"]:
            lines.append("检查缺口：" + safe(issue.get("path", issue.get("tool_id", ""))) + " " + safe(issue["reason"]))
        lines += ["", "本次没有清理、修改 Agent 配置、打开数据库或运行 Agent 命令。", "下一步：按工具核对未分类数据和检查缺口，再单独审查已有普通缓存规则；不要按体检大小直接删除。"]
        if report_path:
            lines.append("完整报告：" + safe(report_path))
        return "\n".join(lines)
    if kind == "scan":
        state = "完整" if result["scan_status"] == "complete" else "部分完成，请查看下方问题"
        disk = result.get("disk_usage", {})
        lines = ["Tidvo 磁盘清理检查", f"扫描状态：{state}",
                 f"磁盘总容量：{size(disk.get('total_bytes'))}；已用：{size(disk.get('used_bytes'))}；可用：{size(disk.get('free_bytes'))}",
                 f"候选总占用：{size(result['candidate_allocated_bytes'])}；待选择项目占用：{size(result['actionable_allocated_bytes'])}",
                 "检查范围：已知缓存和开发产物；候选清单不代表全盘占用分布。",
                 "项目依赖 node_modules、.venv、venv 默认保留。", ""]
        lines += candidates(result["candidates"])
        for issue in result["issues"]:
            lines.append(f"检查问题：{safe(issue['path'])} — {safe(issue['reason'])}")
        lines += ["", "本次只扫描，没有清理文件。待选择项目也不代表已获准清理。"]
        if "agent_audit" in result:
            audit = result["agent_audit"]
            lines.append(f"Agent 体检：发现 {len(audit['detected_tools'])} 类本地数据/应用；状态 {audit['scan_status']}。体检数据仅报告，详见 JSON 中的 agent_audit。")
        if report_path:
            lines += [f"完整 JSON 报告已保存：{safe(report_path)}", "下一步：选择上面的候选 ID，生成待确认计划：",
                      command("plan", "--scan", report_path, "--ids", "候选ID")]
        else:
            lines.append("要生成清理计划，请先加 --output scan.json 重新扫描并保存报告。")
        return "\n".join(lines)
    if kind == "plan":
        lines = [f"待确认计划：{result['id']}", f"估算移入废纸篓容量：{size(result['selected_allocated_bytes'])}", ""]
        lines += candidates(result["candidates"])
        lines += ["", "本次只生成计划，没有清理文件。移入废纸篓通常不会立即释放空间。",
                  "核对并确认上述清单后，执行：", command("apply", "--plan", result["id"], "--confirmed")]
        return "\n".join(lines)
    if kind == "apply":
        lines = [f"操作记录：{result['id']}；状态：{result['status']}",
                 f"已移入废纸篓：{size(result['moved_allocated_bytes'])}"]
        for item in result["entries"]:
            lines.append(f"{item['status']}  {safe(item['source'])}" + (" — " + safe(item["reason"]) if "reason" in item else ""))
        lines += ["移入废纸篓通常不会立即释放空间；未列出的后续项目未执行。",
                  "需要恢复时，先核对记录，再确认运行：", command("restore", "--run", result["id"], "--confirmed")]
        return "\n".join(lines)
    if kind == "restore":
        lines = [f"恢复记录：{result['run_id']}"]
        for item in result["results"]:
            lines.append(f"{item['candidate_id']}  {item['status']}" + (" — " + safe(item["reason"]) if "reason" in item else ""))
        return "\n".join(lines)
    lines = []
    for run in result["runs"]:
        counts = ", ".join(f"{key}={value}" for key, value in Counter(x["status"] for x in run["entries"]).items())
        lines.append(f"{run['id']}  {run['started_at']}  {run['status']}  {counts}")
    return "\n".join(lines) or "暂无清理记录。"
