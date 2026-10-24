"""Mutually exclusive capacity groups; neither candidates nor Trash are savings."""
from .cache_rules import REGENERABLE_RULES

BUCKETS = (
    ("ready_caches", "可生成清理计划的缓存", "核对清单后批量确认；执行时仍检查占用和目录变化"),
    ("quit_app", "需退出应用后复查", "保存并正常退出相关应用，再复查；不保证退出后全部可清"),
    ("separate_review", "需单独确认的产物或旧程序", "说明当前用途、重建或回退影响后单独选择"),
    ("protected", "明确保留的数据或运行环境", "保留依赖、会话、记忆、当前或引用中的工具"),
    ("unverified", "检查不完整或归属待确认", "补全具体缺失证据；不要把未知大小记为零或授权"),
)
CACHES = REGENERABLE_RULES | {"browser.resource_cache", "browser.component_download", "editor.vsix", "editor.compiled_cache",
    "app.page_cache", "developer.npm_prebuild", "project.__pycache__", "project.pytest_cache", "project.mypy_cache", "project.ruff_cache",
    "app.user_temporary", "developer.npm_download"}


def disposition(item):
    notes, activity = set(item.get("evidence", [])), item.get("activity", {})
    if (item.get("agent_protection") or "project_dependency_environment_preserved" in notes or activity.get("configured_reference")
            or item.get("rule_id") in {"project.node_modules", "project.venv"}):
        return "protected"
    if item.get("scan_status") != "complete" or activity.get("activity") == "unknown" or any(n in notes for n in (
            "cache_origin_unverified", "cache_index_unavailable", "application_owner_unknown", "unrecognized_cache_layout",
            "unrecognized_prebuild_entry", "unrecognized_download_entry", "artifact_type_not_confirmed_by_project")):
        return "unverified"
    if activity.get("reference_scan_status") == "partial" and (item.get("packages") or item.get("extension_context")):
        return "unverified"
    if activity.get("activity") == "active":
        return "protected" if item.get("rule_id") == "developer.npx" else "quit_app"
    if item.get("action") != "trash":
        return "protected"
    return "ready_caches" if item.get("rule_id") in CACHES else "separate_review"


def summarize(items):
    groups = {key: {"id": key, "label": label, "next_action": action, "count": 0,
                   "measured_allocated_bytes": 0, "unknown_size_count": 0, "lower_bound_count": 0, "owners": {}}
              for key, label, action in BUCKETS}
    for item in items:
        key = disposition(item)
        item["disposition"] = key
        group = groups[key]
        group["count"] += 1
        value = item.get("allocated_bytes")
        group["unknown_size_count"] += value is None
        group["measured_allocated_bytes"] += value or 0
        group["lower_bound_count"] += bool(item.get("size_observation", {}).get("lower_bound"))
        owner = item.get("owner") or item.get("rule_id", "unknown")
        entry = group["owners"].setdefault(owner, {"count": 0, "measured_allocated_bytes": 0})
        entry["count"] += 1
        entry["measured_allocated_bytes"] += value or 0
    return {"scope": "deduplicated_known_candidates_only", "buckets": list(groups.values()),
            "measured_allocated_bytes": sum(g["measured_allocated_bytes"] for g in groups.values()),
            "unknown_size_count": sum(g["unknown_size_count"] for g in groups.values()),
            "note": "分类容量为已识别候选估算，不是保证释放空间；原生预览和 Agent 体检容量不相加"}
