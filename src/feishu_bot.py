"""
================================================================================
飞书推送模块 (feishu_bot.py)
================================================================================
职责：通过飞书企业自建应用机器人向指定用户推送交互式卡片消息。

鉴权机制（v2.0 变更，区别于旧版 webhook）：
  webhook 模式 → HMAC-SHA256 签名 + URL
  企业自建应用  → app_id + app_secret 换取 tenant_access_token（有效期 7200s）
                  用 token 调用消息 API

设计要点：
  1. Token 缓存：避免每次推送都重新获取 token（缓存 7200s，提前 300s 刷新）
  2. 卡片构建与推送分离：build_xxx_card() 只负责内容，send_card() 只负责网络
  3. Markdown 分片：优先在 ## 标题处切割，保证排版完整
  4. 重试机制：单次推送失败最多重试 3 次

修改指南：
  - 调整卡片样式：修改 config/settings.json 中的 card_char_limit/color 字段
  - 修改摘要标签：修改 settings.json 中的 summary_labels
  - 调整分片策略：修改 split_markdown() 中的切割逻辑
================================================================================
"""

import json, time as time_module
import urllib.request


# ══════════════════════════════════════════════════════════════
# Token 管理
# ══════════════════════════════════════════════════════════════

# 内存缓存：避免每次推送都重新获取 token
# token 有效期 7200 秒（2 小时），提前 300 秒（5 分钟）刷新
_token_cache = {"token": "", "expires_at": 0}


def _get_tenant_access_token(app_id, app_secret):
    """获取飞书 tenant_access_token，带缓存复用。
    
    每次调用先检查缓存是否有效，有效则直接返回。
    缓存过期时自动重新请求，并更新缓存时间戳。
    
    Args:
        app_id:     飞书应用 App ID（从环境变量 FEISHU_APP_ID 读取）
        app_secret: 飞书应用 App Secret
    
    Returns:
        str: 有效的 tenant_access_token
    
    Raises:
        RuntimeError: 飞书 API 返回非 0 code
    """
    now = time_module.time()
    # 缓存有效 → 直接返回
    if _token_cache["token"] and now < _token_cache["expires_at"] - 300:
        return _token_cache["token"]

    # 缓存过期 → 重新获取
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
    """构建单张飞书交互式卡片的 JSON 对象。
    
    飞书消息 API 的卡片格式与 webhook 略有不同：
    - 不需要外层 "card" 包装
    - content 字段需要 JSON-stringify
    
    Args:
        title:   卡片标题（最长 80 字符，超出自动截断）
        content: 卡片正文（Markdown 格式）
        color:   顶部色条（blue/green/red/turquoise/purple 等）
    
    Returns:
        dict: 飞书卡片 JSON 对象
    """
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
    """通过飞书企业自建应用推送交互式卡片消息。
    
    失败时自动重试（默认 3 次），间隔 2 秒。
    重试时会重新获取 token，避免因 token 过期导致的连锁失败。
    
    Args:
        app_id:     飞书 App ID
        app_secret: 飞书 App Secret
        receive_id: 接收者的 open_id（从环境变量 FEISHU_RECEIVE_ID 读取）
        title:      卡片标题
        content:    卡片 Markdown 正文
        color:      色条颜色
        retries:    最大重试次数（默认 3）
    
    Returns:
        bool: True=推送成功, False=全部重试后仍失败
    """
    token = _get_tenant_access_token(app_id, app_secret)
    card = _build_card_json(title, content, color)

    # 构造飞书消息 API 请求体
    # 注意：content 字段是 JSON 字符串嵌套（card JSON → string → body JSON）
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    body = json.dumps({
        "receive_id": receive_id,
        "msg_type":   "interactive",
        "content":    json.dumps(card, ensure_ascii=False),
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
                return True  # 推送成功
            # code != 0，可能是 token 过期或其他业务错误
            if attempt < retries - 1:
                _sleep(2)
                token = _get_tenant_access_token(app_id, app_secret)  # 重新获取 token
        except Exception:
            if attempt < retries - 1:
                _sleep(2)
                token = _get_tenant_access_token(app_id, app_secret)
    return False  # 全部重试失败


def send_alert(app_id, app_secret, receive_id, message):
    """推送纯文本故障告警消息（用于全局异常捕获）。
    
    与 send_card() 的区别：
    - msg_type 为 "text" 而非 "interactive"
    - 无重试逻辑（告警失败不阻塞主流程）
    - 用于脚本崩溃时通知用户排查问题
    
    Args:
        app_id:     飞书 App ID
        app_secret: 飞书 App Secret
        receive_id: 接收者 open_id
        message:    告警消息文本
    """
    token = _get_tenant_access_token(app_id, app_secret)
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    body = json.dumps({
        "receive_id": receive_id,
        "msg_type":   "text",
        "content":    json.dumps({
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
            pass  # 告警推送成功，不需要处理响应
    except Exception:
        pass  # 告警失败不阻塞，静默跳过


# ══════════════════════════════════════════════════════════════
# Markdown 分片（解决飞书单卡片 4500 字符限制）
# ══════════════════════════════════════════════════════════════

def split_markdown(content, limit=4500):
    """将长文本智能拆分为多张卡片，优先在二级标题处切割。
    
    飞书交互式卡片单张最多约 4500 字符（实际限制取决于内容复杂度）。
    此函数的分片策略：
      1. 先按 ## 标题分节（保证语义完整）
      2. 如果某节仍超限，按字符硬切（保底方案）
    
    Args:
        content: 需分片的 Markdown 文本
        limit:   单卡片最大字符数（可在 settings.json 中覆盖）
    
    Returns:
        list[str]: 分片后的文本列表
    """
    if not content:
        return []
    if len(content) <= limit:
        return [content]  # 无需分片

    # 第 1 步：按 ## 标题分节
    chunks = []
    current = ""
    # split 后第一段不包含 ## 前缀（是标题前的内容），后续段落需要补回
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

    # 第 2 步：对仍然超限的片段按字符硬切（极端情况保底）
    final = []
    for c in chunks:
        if len(c) <= limit:
            final.append(c)
        else:
            for i in range(0, len(c), limit):
                final.append(c[i:i + limit])
    return final


# ══════════════════════════════════════════════════════════════
# 卡片内容构建（与主流程解耦，纯数据转换）
# ══════════════════════════════════════════════════════════════

def build_summary_card(ai_result, today_full, settings):
    """构建摘要卡片（每日推送的第 1 张卡片）。
    
    包含：报告标题（从 settings.report_title 读取）、
    AI 生成的核心结论和关键要点。
    
    Args:
        ai_result:  AI 分析结果字典
        today_full: 完整日期字符串（如 "2026-07-26"）
        settings:   settings 配置字典
    
    Returns:
        tuple: (title, content, color) 三元素元组
    """
    report_title = settings.get("report_title", "\u6bcf\u65e5\u60c5\u62a5")

    # 降级模式：AI 返回纯文本而非结构化数据
    if ai_result.get("raw"):
        return (
            f"{report_title} - {today_full}",
            settings.get("no_news_text", "\u6458\u8981\u751f\u6210\u5931\u8d25\uff0c\u8be6\u89c1\u6b63\u6587\u5361\u7247\u3002"),
            settings.get("no_news_card_color", "red"),
        )

    headline   = ai_result.get("headline", "")
    key_points = ai_result.get("key_points", [])
    # 摘要标签可配置（settings.json → summary_labels）
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
        f"{report_title} - {today_full}",
        "\n".join(lines),
        settings.get("summary_card_color", "blue"),
    )


def build_source_cards(articles, today, settings):
    """构建信源卡片（按地区分组展示所有新闻）。
    
    工作流程：
      1. 按 region_buckets 配置将文章分到不同地区组
      2. 每组生成一个 Markdown 区块（## 组名）
      3. 自动分片：当累积量超过 card_char_limit 时另起一张卡片
      4. 返回 (title, content, color) 列表，由主流程逐张推送
    
    Args:
        articles: 文章列表
        today:    日期短格式（如 "07"，用于卡片标题）
        settings: settings 配置字典
    
    Returns:
        list[tuple]: 每项为 (title, content, color)
    """
    flags       = settings["region_flags"]
    buckets_def = settings["region_buckets"]
    char_limit  = settings.get("card_char_limit", 4500)

    # 第 1 步：按地区分组
    buckets = {name: [] for name in buckets_def}
    for a in articles:
        placed = False
        for name, regs in buckets_def.items():
            if a["region"] in regs:
                buckets[name].append(a)
                placed = True
                break
        if not placed and "\u5176\u4ed6" in buckets:
            buckets["\u5176\u4ed6"].append(a)  # 未匹配的文章归入"其他"

    # 第 2 步：生成卡片（自动分片）
    cards = []
    current = ""
    current_len = 0
    card_idx = 1

    def flush():
        """将当前累积的内容输出为一张卡片。"""
        nonlocal current, current_len, card_idx
        if current.strip():
            title = f"Sources {card_idx} - {today}"
            # 第 1 张和第 2+ 张使用不同颜色
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
            continue  # 跳过分组中没有文章的组
        header = f"## {name}\n\n"
        if current_len + len(header) > char_limit and current:
            flush()  # 当前卡片装不下，先输出
        current += header
        current_len += len(header)

        for a in items:
            global_idx += 1
            flag = flags.get(a["region"], "")
            # 标题截断到 65 字符（避免单条过长撑破排版）
            t = a["title"][:65] + ("..." if len(a["title"]) > 65 else "")
            line = (
                f"{global_idx}. [{flag}] [{t}]({a['url']})\n"
                f"   *{a['source']}*\n\n"
            )
            if current_len + len(line) > char_limit:
                flush()  # 当前卡片装不下，新建一张
            current += line
            current_len += len(line)
    flush()  # 输出最后一张卡片的剩余内容
    return cards
