"""
================================================================================
通用工具模块 (utils.py)
================================================================================
职责：提供所有业务模块共享的底层工具函数，不包含任何业务逻辑。
包含：
  - HTTP GET/POST 请求封装
  - 多格式 RSS 日期解析（解决不同信源日期格式不一致的问题）

修改指南：
  - 如果要添加新的 HTTP 方法（如 PUT/DELETE），在此文件中新增函数
  - 如果遇到新的 RSS 日期格式无法解析，在 _RSS_TIME_FORMATS 列表末尾追加即可
================================================================================
"""

import json
import urllib.request
from datetime import datetime


# ── HTTP 请求封装 ──────────────────────────────────────────────

def http_get(url, headers=None, timeout=30):
    """HTTP GET 请求，返回解码后的文本字符串。
    
    Args:
        url:     请求地址
        headers: 额外的请求头字典（可选，默认仅 User-Agent）
        timeout: 超时秒数（默认 30s）
    
    Returns:
        str: 响应体文本
    
    Raises:
        urllib.error.URLError: 网络错误或超时
    """
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def http_post_json(url, payload, headers=None, timeout=120):
    """HTTP POST JSON 请求，返回解析后的字典。
    
    Args:
        url:     请求地址
        payload: 请求体字典（自动转为 JSON 字符串）
        headers: 额外的请求头（Content-Type 会自动添加）
        timeout: 超时秒数（默认 120s，AI 调用可能较慢）
    
    Returns:
        dict: 解析后的响应 JSON
    """
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    h = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ── 多格式 RSS 时间解析 ───────────────────────────────────────
# 不同信源的 RSS 日期格式千差万别，此处列出常见格式逐一尝试。
# 如果遇到新的格式无法识别，在列表末尾添加即可，无需改动其他代码。

_RSS_TIME_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %Z",   # RFC 2822 标准格式（如 "Mon, 05 Jan 2026 10:30:00 GMT"）
    "%a, %d %b %Y %H:%M:%S %z",   # RFC 2822 带数字时区偏移
    "%Y-%m-%dT%H:%M:%S%z",        # ISO 8601 带时区
    "%Y-%m-%dT%H:%M:%SZ",         # ISO 8601 UTC
    "%Y-%m-%dT%H:%M:%S",          # ISO 8601 无时区
    "%Y-%m-%d %H:%M:%S",          # 常见数据库格式
    "%a, %d %b %Y %H:%M:%S",      # RFC 2822 无时区
    "%d %b %Y %H:%M:%S %Z",       # 日在前、月名在后的格式
]


def parse_rss_date(date_str):
    """尝试多种格式解析 RSS 日期字符串，全部失败返回 datetime.min。
    
    这个函数是解决"旧新闻置顶、新资讯下沉"问题的核心。
    之前只支持一种格式，不同信源的日期解析失败后被排到最后。
    现在依次尝试 8 种格式，覆盖绝大多数 RSS 源。
    
    Args:
        date_str: RSS pubDate 字段的原始字符串
    
    Returns:
        datetime: 解析成功返回对应时间，失败返回 datetime.min（排到最后）
    """
    if not date_str:
        return datetime.min
    date_str = date_str.strip()
    for fmt in _RSS_TIME_FORMATS:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return datetime.min
