"""飞书企业自建应用机器人推送模块 —— tenant_access_token 鉴权"""

import json, time as time_module
import urllib.request

# ══════════════════════════════════════════════════════════════
# Token 缓存（有效期 7200s，提前 5 分钟刷新）
# ══════════════════════════════════════════════════════════════
_token_cache = {"token": "", "expires_at": 0}


def _get_tenant_access_token(app_id, app_secret):
    """获取 tenant_access_token，带缓存复用。"""
    now = time_module.time()
    if _token_cache["token"] and now < _token_cache["expires_at"] - 300:
        return _token_cache["token"]

    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    body = json.dumps({
        "app_id": app_id,
        "app_secret": app_secret,
    }).encode()
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


# ══════════════════════════════════════════════════════════════
# 消息推送
# ══════════════════════════════════════════════════════════════
def _build_card_json(title, content, color):
    """构建飞书卡片 JSON 对象（消息 API 格式，无 card 外层包装）。"""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title[:80]},
            "template": color,
        },
        "elements": [{"tag": "markdown", "content": content}],
    }


def send_card(app_id, app_secret, receive_id, title, content, color,
              retries=3, _sleep=time_module.sleep):
    """通过企业自建应用机器人推送交互式卡片。

    Args:
        app_id: 飞书应用 App ID
        app_secret: 飞书应用 App Secret
        receive_id: 接收者 open_id
        title: 卡片标题
        content: Markdown 内容
        color: 卡片顶部色条
        retries: 重试次数

    Returns:
        bool: 推送成功返回 True
    """
    token = _get_tenant_access_token(app_id, app_secret)
    card = _build_card_json(title, content, color)

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
                _sleep(2)
                token = _get_tenant_access_token(app_id, app_secret)
        except Exception:
            if attempt < retries - 1:
                _sleep(2)
                token = _get_tenant_access_token(app_id, app_secret)
    return False


def send_alert(app_id, app_secret, receive_id, message):
    """推送纯文本故障告警。"""
    token = _get_tenant_access_token(app_id, app_secret)
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    body = json.dumps({
        "receive_id": receive_id,
        "msg_type": "text",
        "content": json.dumps({
            "text": f"\u26a0\ufe0f \u71c3\u6599\u7535\u6c60\u60c5\u62a5\u811a\u672c\u5f02\u5e38\n\n{message}"
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


# ══════════════════════════════════════════════════════════════
# 卡片构建（与 webhook 版完全一致的 UI 逻辑）
# ══════════════════════════════════════════════════════════════
def split_markdown(content, limit=4500):
    """智能 Markdown 分片：优先在 ## 二级标题处切割。"""
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


def build_summary_card(ai_result, today_full, settings):
    if ai_result.get("raw"):
        return (
            f"{report_title} - {today_full}",
            settings.get("no_news_text", "\u6458\u8981\u751f\u6210\u5931\u8d25\uff0c\u8be6\u89c1\u6b63\u6587\u5361\u7247\u3002"),
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

    lines += ["", "## \u4eca\u65e5\u91cd\u70b9", ""]
    for i, kp in enumerate(key_points, 1):
        lines.append(f"{i}. {kp}")

    return (
        f"Fuel Cell Intelligence - {today_full}",
        "\n".join(lines),
        settings.get("summary_card_color", "blue"),
    )


def build_source_cards(articles, today, settings):
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
            line = (
                f"{global_idx}. [{flag}] [{t}]({a['url']})\n"
                f"   *{a['source']}*\n\n"
            )
            if current_len + len(line) > char_limit:
                flush()
            current += line
            current_len += len(line)
    flush()
    return cards
    report_title = settings.get("report_title", "Daily Intelligence")
