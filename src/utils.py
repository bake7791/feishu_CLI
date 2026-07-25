"""通用工具模块 —— HTTP 请求、时间解析、文本处理"""

import json
import urllib.request
from datetime import datetime

# ── HTTP ──
def http_get(url, headers=None, timeout=30):
    """HTTP GET 请求，返回解码后的文本。"""
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def http_post_json(url, payload, headers=None, timeout=120):
    """HTTP POST JSON 请求，返回解析后的 dict。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    h = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ── 多格式 RSS 时间解析 ──
_RSS_TIME_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %Z",   # RFC 2822 with named TZ
    "%a, %d %b %Y %H:%M:%S %z",   # RFC 2822 with offset
    "%Y-%m-%dT%H:%M:%S%z",        # ISO 8601 with tz
    "%Y-%m-%dT%H:%M:%SZ",         # ISO 8601 UTC
    "%Y-%m-%dT%H:%M:%S",          # ISO 8601 no tz
    "%Y-%m-%d %H:%M:%S",          # Simple datetime
    "%a, %d %b %Y %H:%M:%S",      # RFC 2822 no TZ
    "%d %b %Y %H:%M:%S %Z",       # 01 Jan 2025 10:30:00 GMT
]


def parse_rss_date(date_str):
    """尝试多种格式解析 RSS 日期字符串。

    Args:
        date_str: RSS pubDate 字段值

    Returns:
        datetime: 解析成功返回对应时间，全部失败返回 datetime.min
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
