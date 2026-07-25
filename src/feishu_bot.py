"""飞书机器人推送模块 —— 签名、卡片构建、推送、分片"""

import json, base64, hmac, hashlib, time as time_module
import urllib.request

# ══════════════════════════════════════════════════════════════
# HMAC 签名（修复：传入实际请求 Body）
# ══════════════════════════════════════════════════════════════
def feishu_sign(timestamp, secret, body_bytes):
    """飞书官方签名算法：HMAC-SHA256(timestamp\nsecret, request_body)

    重要：第二个参数必须传入请求 Body 的实际字节，
    空字节会导致飞书服务端拦截所有消息。
    """
    string_to_sign = (timestamp + "\n" + secret).encode("utf-8")
    return base64.b64encode(
        hmac.new(string_to_sign, body_bytes, hashlib.sha256).digest()
    ).decode()


# ══════════════════════════════════════════════════════════════
# 推送函数
# ══════════════════════════════════════════════════════════════
def send_card(webhook_url, feishu_secret, title, content, color,
              retries=3, _sleep=time_module.sleep):
    """推送飞书交互式卡片。

    Args:
        webhook_url: 飞书 Webhook 地址
        feishu_secret: 签名密钥
        title: 卡片标题（最长 80 字符）
        content: Markdown 内容
        color: 卡片顶部色条（blue/green/red/turquoise/purple 等）
        retries: 重试次数
        _sleep: 延迟函数（便于测试注入）

    Returns:
        bool: 推送成功返回 True
    """
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title[:80]},
                "template": color,
            },
            "elements": [{"tag": "markdown", "content": content}],
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    for attempt in range(retries):
        ts = str(int(time_module.time()))
        sig = feishu_sign(ts, feishu_secret, data)
        url = f"{webhook_url}?timestamp={ts}&sign={sig}"

        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
            if result.get("code") == 0:
                return True
            if attempt < retries - 1:
                _sleep(2)
        except Exception:
            if attempt < retries - 1:
                _sleep(2)
    return False


def send_alert(webhook_url, feishu_secret, message):
    """推送纯文本故障告警（用于全局异常捕获）。

    Args:
        webhook_url: 飞书 Webhook 地址
        feishu_secret: 签名密钥
        message: 告警消息
    """
    payload = {
        "msg_type": "text",
        "content": {
            "text": f"\u26a0\ufe0f \u71c3\u6599\u7535\u6c60\u60c5\u62a5\u811a\u672c\u5f02\u5e38\n\n{message}"
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ts = str(int(time_module.time()))
    sig = feishu_sign(ts, feishu_secret, data)
    url = f"{webhook_url}?timestamp={ts}&sign={sig}"

    try:
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15):
            pass
    except Exception:
        pass  # 告警推送失败不阻塞主流程


# ══════════════════════════════════════════════════════════════
# 卡片构建
# ══════════════════════════════════════════════════════════════
def split_markdown(content, limit=4500):
    """智能 Markdown 分片：优先在 ## 二级标题处切割，保持排版完整。

    Args:
        content: Markdown 文本
        limit: 单卡片最大字符数

    Returns:
        list[str]: 分片后的文本列表
    """
    if not content:
        return []
    if len(content) <= limit:
        return [content]

    # 第一步：按 ## 标题分节
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

    # 第二步：对仍然超限的片段按字符硬切
    final = []
    for c in chunks:
        if len(c) <= limit:
            final.append(c)
        else:
            for i in range(0, len(c), limit):
                final.append(c[i:i + limit])
    return final


def build_summary_card(ai_result, today_full, settings):
    """构建摘要卡片。

    Args:
        ai_result: AI 分析结果
        today_full: 完整日期字符串
        settings: settings 配置

    Returns:
        (title, content, color)
    """
    if ai_result.get("raw"):
        return (
            f"Fuel Cell Intelligence - {today_full}",
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
    """按地区分组构建信源卡片。

    Args:
        articles: 文章列表
        today: 日期短格式 (MM)
        settings: settings 配置

    Returns:
        list[(title, content, color)]
    """
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
