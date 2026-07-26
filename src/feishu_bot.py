"""
================================================================================
飞书推送模块 (feishu_bot.py) — 企业自建应用增强版
================================================================================
职责：通过飞书企业自建应用向指定用户推送交互式卡片消息，支持：
  - 纯 Markdown 卡片（原有功能）
  - 多元素卡片（column_set KPI 看板 + img 图表 + markdown）
  - 图片上传（im/v1/images → image_key）
  - 故障告警

鉴权：app_id + app_secret 换取 tenant_access_token（缓存 7200s）

自建应用相比群机器人 Webhook 的核心优势：
  - 能上传图片并在卡片中嵌入（Webhook 无法获取 image_key）
  - 能用 column_set 做多列 KPI 看板
  - 能推送富文本、交互按钮等
================================================================================
"""

import json
import os
import uuid
import time as time_module
import urllib.request


# ================================================================
# Token 管理
# ================================================================

_token_cache = {"token": "", "expires_at": 0}


def _get_tenant_access_token(app_id, app_secret):
    """获取飞书 tenant_access_token，带缓存复用。

    token 有效期 7200 秒，提前 300 秒刷新。
    """
    now = time_module.time()
    if _token_cache["token"] and now < _token_cache["expires_at"] - 300:
        return _token_cache["token"]

    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    body = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        resp = json.loads(r.read().decode())

    if resp.get("code") != 0:
        raise RuntimeError(f"获取 tenant_access_token 失败: {resp}")

    _token_cache["token"] = resp["tenant_access_token"]
    _token_cache["expires_at"] = now + resp.get("expire", 7200)
    return _token_cache["token"]


# ================================================================
# 图片上传（自建应用核心优势）
# ================================================================

def _build_multipart(fields, files):
    """构造 multipart/form-data 请求体。

    Args:
        fields: 普通字段 {name: value}
        files:  文件字段 {name: (filename, filebytes)}

    Returns:
        (body_bytes, content_type_header)
    """
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(f"{value}\r\n".encode())
    for name, (filename, filedata) in files.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        parts.append(b"Content-Type: image/png\r\n\r\n")
        parts.append(filedata)
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    return body, f"multipart/form-data; boundary={boundary}"


def upload_image(app_id, app_secret, image_path, retries=2):
    """上传 PNG 图片到飞书，返回 image_key。

    这是自建应用相比 Webhook 的核心能力：通过 im/v1/images 接口
    上传图片获取 image_key，然后在卡片中用 img 元素嵌入。

    需要应用具备 im:image 权限。

    Args:
        app_id:     飞书 App ID
        app_secret: 飞书 App Secret
        image_path: PNG 文件路径
        retries:    重试次数

    Returns:
        str: image_key，失败返回 None
    """
    with open(image_path, "rb") as f:
        image_data = f.read()

    for attempt in range(retries):
        token = _get_tenant_access_token(app_id, app_secret)
        body, ct = _build_multipart(
            {"image_type": "message"},
            {"image": ("chart.png", image_data)},
        )
        url = "https://open.feishu.cn/open-apis/im/v1/images"
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": ct, "Authorization": f"Bearer {token}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.loads(r.read().decode())
            if resp.get("code") == 0:
                return resp["data"]["image_key"]
        except Exception:
            if attempt < retries - 1:
                time_module.sleep(2)
    return None


# ================================================================
# 卡片构建
# ================================================================

def _build_card_json(title, content, color):
    """构建单 markdown 元素的交互卡片。"""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title[:80]},
            "template": color,
        },
        "elements": [{"tag": "markdown", "content": content}],
    }


def _build_elements_card(title, elements, color):
    """构建多元素交互卡片（支持 column_set / img / markdown 混排）。"""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title[:80]},
            "template": color,
        },
        "elements": elements,
    }


def _img_element(image_key, alt_text="chart"):
    """构建图片元素。"""
    return {
        "tag": "img",
        "img_key": image_key,
        "alt": {"tag": "plain_text", "content": alt_text},
    }


# ================================================================
# 消息推送
# ================================================================

def _send_message(app_id, app_secret, receive_id, card, retries=3):
    """底层消息发送：推送卡片 JSON 到飞书 im/v1/messages。"""
    token = _get_tenant_access_token(app_id, app_secret)
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    body = json.dumps({
        "receive_id": receive_id,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }, ensure_ascii=False).encode()

    for attempt in range(retries):
        req = urllib.request.Request(
            url, data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
            if result.get("code") == 0:
                return True
            if attempt < retries - 1:
                time_module.sleep(2)
                token = _get_tenant_access_token(app_id, app_secret)
        except Exception:
            if attempt < retries - 1:
                time_module.sleep(2)
                token = _get_tenant_access_token(app_id, app_secret)
    return False


def send_card(app_id, app_secret, receive_id, title, content, color,
              retries=3):
    """推送单 markdown 卡片（兼容原有接口）。"""
    card = _build_card_json(title, content, color)
    return _send_message(app_id, app_secret, receive_id, card, retries)


def send_elements_card(app_id, app_secret, receive_id, title, elements, color,
                       retries=3):
    """推送多元素卡片（column_set / img / markdown 混排）。

    这是增强版推送函数，支持飞书交互卡片的全部元素类型。
    """
    card = _build_elements_card(title, elements, color)
    return _send_message(app_id, app_secret, receive_id, card, retries)


def send_alert(app_id, app_secret, receive_id, message):
    """推送纯文本故障告警。"""
    token = _get_tenant_access_token(app_id, app_secret)
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    body = json.dumps({
        "receive_id": receive_id,
        "msg_type": "text",
        "content": json.dumps({
            "text": f"\u26a0\ufe0f \u60c5\u62a5\u811a\u672c\u5f02\u5e38\n\n{message}"
        }, ensure_ascii=False),
    }, ensure_ascii=False).encode()
    try:
        req = urllib.request.Request(
            url, data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15):
            pass
    except Exception:
        pass


# ================================================================
# Markdown 分片
# ================================================================

def split_markdown(content, limit=4500):
    """将长文本智能拆分为多张卡片，优先在二级标题处切割。"""
    if not content:
        return []
    if len(content) <= limit:
        return [content]

    chunks = []
    current = ""
    sections = content.split("\n## ")
    for idx, sec in enumerate(sections):
        prefix = "## " if idx > 0 else ""
        seg = prefix + sec
        if len(current) + len(seg) > limit and current:
            chunks.append(current.rstrip())
            current = seg
        else:
            current += seg
    if current.strip():
        chunks.append(current.rstrip())

    final = []
    for c in chunks:
        if len(c) <= limit:
            final.append(c)
        else:
            for i in range(0, len(c), limit):
                final.append(c[i:i + limit])
    return final


# ================================================================
# 卡片内容构建
# ================================================================

def build_summary_card(ai_result, today_full, settings):
    """构建摘要卡片（AI 核心结论 + 关键要点）。"""
    report_title = settings.get("report_title", "\u6bcf\u65e5\u60c5\u62a5")
    if ai_result.get("raw"):
        return (
            f"{report_title} - {today_full}",
            settings.get("no_news_text", "\u6458\u8981\u751f\u6210\u5931\u8d25"),
            settings.get("no_news_card_color", "red"),
        )

    headline = ai_result.get("headline", "")
    key_points = ai_result.get("key_points", [])
    labels = settings.get("summary_labels",
                          ["\u6700\u5173\u952e\u4fe1\u53f7", "\u6700\u5927\u673a\u4f1a", "\u6700\u5927\u98ce\u9669"])

    lines = ["## \u4eca\u65e5\u5b9a\u8c03", ""]
    for i, line in enumerate(headline.split("\n")):
        label = labels[i] if i < len(labels) else f"\u7b2c{i+1}\u70b9"
        lines.append(f"**{label}**\uff1a{line.strip()}")

    # 情绪指数（新增）
    sentiment = ai_result.get("sentiment_index")
    if sentiment is not None:
        bar_on = "\u258c"
        bar_off = "\u2592"
        lines += ["", "## \u4eca\u65e5\u60c5\u7eea", ""]
        lines.append(f"\u7efc\u5408\u60c5\u7eea\u6307\u6570: **{sentiment:+.1f}/10**")
        bars_filled = int((sentiment + 10) / 20 * 10)
        bars_filled = max(0, min(10, bars_filled))
        lines.append(f"`{bar_on * bars_filled}{bar_off * (10 - bars_filled)}`")

    lines += ["", "## \u4eca\u65e5\u91cd\u70b9", ""]
    for i, kp in enumerate(key_points, 1):
        lines.append(f"{i}. {kp}")

    return (
        f"{report_title} - {today_full}",
        "\n".join(lines),
        settings.get("summary_card_color", "blue"),
    )


def build_source_cards(articles, today, settings):
    """构建信源卡片（按地区分组）。"""
    flags = settings["region_flags"]
    buckets_def = settings["region_buckets"]
    char_limit = settings.get("card_char_limit", 4500)

    buckets = {name: [] for name in buckets_def}
    for a in articles:
        placed = False
        for name, regs in buckets_def.items():
            if a["region"] in regs:
                buckets[name].append(a)
                placed = True
                break
        if not placed and "\u5176\u4ed6" in buckets:
            buckets["\u5176\u4ed6"].append(a)

    cards = []
    current = ""
    current_len = 0
    card_idx = 1

    def flush():
        nonlocal current, current_len, card_idx
        if current.strip():
            title = f"Sources {card_idx} - {today}"
            color = (
                settings["source_card_color_1"] if card_idx == 1
                else settings.get("source_card_color_2", "purple")
            )
            cards.append((title, current.strip(), color))
            card_idx += 1
        current = ""
        current_len = 0

    global_idx = 0
    for name in buckets_def:
        items = buckets[name]
        if not items:
            continue
        header = f"## {name}\n\n"
        if current_len + len(header) > char_limit and current:
            flush()
        current += header
        current_len += len(header)
        for a in items:
            global_idx += 1
            flag = flags.get(a["region"], "")
            t = a["title"][:65] + ("..." if len(a["title"]) > 65 else "")
            line = f"{global_idx}. [{flag}] [{t}]({a['url']})\n   *{a['source']}*\n\n"
            if current_len + len(line) > char_limit:
                flush()
            current += line
            current_len += len(line)
    flush()
    return cards


# ================================================================
# KPI 看板卡片（新增 — 发挥自建应用 column_set 优势）
# ================================================================

def build_kpi_elements(market_data, settings):
    """构建 KPI 看板的 column_set 元素列表。

    用飞书卡片的 column_set 做多列 KPI 看板，每个品种一列，
    显示价格、涨跌幅和来源。涨用红底色 ▲，跌用绿底色 ▼。

    Returns:
        list: 卡片元素列表，空列表表示无数据
    """
    items = market_data.get("items", [])
    if not items:
        return []

    columns = []
    for item in items[:4]:
        change = item.get("change", 0) or 0
        pct = item.get("change_pct", 0) or 0
        arrow = "\u25b2" if change >= 0 else "\u25bc"
        price = item["price"]
        price_str = f"{price:,.0f}" if price >= 100 else f"{price:,.2f}"
        unit = item.get("unit", "")
        content = (
            f"**{item['name']}**\n"
            f"{price_str} {unit}\n"
            f"{arrow} {pct:+.2f}%\n"
            f"*{item.get('source', '')}*"
        )
        columns.append({
            "tag": "column",
            "elements": [{"tag": "markdown", "content": content}],
            "width": "weighted",
            "weight": 1,
        })

    return [{"tag": "column_set", "columns": columns}] if columns else []


def build_data_table(market_data):
    """构建数据明细 Markdown 表格。

    Returns:
        str: Markdown 表格文本，空字符串表示无数据
    """
    items = market_data.get("items", [])
    if not items:
        return ""

    lines = [
        "| \u54c1\u79cd | \u6700\u65b0\u4ef7 | \u6da8\u8dcc | \u6da8\u8dcc\u5e45 | \u6765\u6e90 |",
        "|------|--------|------|--------|------|",
    ]
    for item in items:
        change = item.get("change", 0) or 0
        pct = item.get("change_pct")
        arrow = "\u25b2" if change >= 0 else "\u25bc"
        price = item["price"]
        price_str = f"{price:,.0f}" if price >= 100 else f"{price:,.2f}"
        unit = item.get("unit", "")
        change_str = f"{arrow}{abs(change):,.0f}" if change else "-"
        pct_str = f"{pct:+.2f}%" if pct is not None else "-"
        lines.append(
            f"| {item['name']} | {price_str} {unit} | {change_str} | {pct_str} | {item.get('source', '')} |"
        )
    return "\n".join(lines)


def build_chart_elements(image_keys, settings):
    """构建图表卡片元素列表（图片 + 标题）。

    Args:
        image_keys: [(label, image_key), ...] 图片列表

    Returns:
        list: 卡片元素列表
    """
    elements = []
    for label, key in image_keys:
        if not key:
            continue
        if label:
            elements.append({
                "tag": "markdown",
                "content": f"**{label}**",
            })
        elements.append(_img_element(key, alt_text=label or "chart"))
    return elements
