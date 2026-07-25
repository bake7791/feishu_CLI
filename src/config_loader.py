"""配置加载与校验模块"""

import json
import os
from pathlib import Path


def load_settings(config_dir, name, required_keys):
    """加载 JSON 配置文件并校验必填字段。"""
    file = config_dir / name
    if not file.exists():
        raise FileNotFoundError(
            f"配置文件不存在: {file}\n"
            f"请复制 {name.replace('.json', '.example.json')} "
            f"并修改为 {name}"
        )

    with open(file, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    errors = []
    for key, desc in required_keys:
        if key not in data:
            errors.append(
                f"  - [{key}] {desc}\n"
                f"请参考 {name.replace('.json', '.example.json')}"
            )

    if errors:
        msg = (
            f"配置文件 {file} 校验失败，"
            f"缺少以下必填字段：\n"
            + "\n".join(errors)
        )
        raise ValueError(msg)

    return data


def load_text(config_dir, name):
    """加载纯文本配置文件。"""
    file = config_dir / name
    if not file.exists():
        raise FileNotFoundError(
            f"文本文件不存在: {file}\n"
            f"请复制 {name.replace('.txt', '.example.txt')} "
            f"并修改为 {name}"
        )
    with open(file, "r", encoding="utf-8-sig") as f:
        return f.read()


def load_prompt_fallback(config_dir):
    """加载降级提示词，文件不存在时返回内置默认值。"""
    try:
        return load_text(config_dir, "prompt_fallback.txt")
    except FileNotFoundError:
        return (
            "基于以下新闻撰写五段式 Markdown 情报简报"
            "（政策/技术/竞争/市场/行动建议）：\n"
            "{articles_text}"
        )


def load_all(config_dir):
    """加载全部配置文件并返回统一配置对象。"""
    settings = load_settings(config_dir, "settings.json", [
        ("ceid_map",       "Google News 国家/语言映射"),
        ("region_flags",   "地区国旗 emoji 映射"),
        ("region_buckets", "地区分组规则"),
        ("ai_endpoint",    "AI API 端点地址"),
        ("ai_model",       "AI 模型名称"),
        ("max_tokens",     "AI 最大输出 token"),
        ("temperature",    "AI 温度参数"),
    ])

    sources = load_settings(config_dir, "sources.json", [
        ("queries",      "Google News 检索词列表"),
        ("max_articles", "最大采集文章数量"),
    ])

    prompt_system   = load_text(config_dir, "prompt_system.txt")
    prompt_user     = load_text(config_dir, "prompt_user.txt")
    prompt_fallback = load_prompt_fallback(config_dir)

    # 飞书企业自建应用凭证
    app_id     = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    receive_id = os.environ.get("FEISHU_RECEIVE_ID", "")

    # AI Token (GitHub Models 优先用 GITHUB_TOKEN)
    ai_api_token = (
        os.environ.get("AI_API_TOKEN")
        or os.environ.get("GITHUB_TOKEN", "")
    )

    return {
        "settings":        settings,
        "sources":         sources,
        "prompt_system":   prompt_system,
        "prompt_user":     prompt_user,
        "prompt_fallback": prompt_fallback,
        "app_id":          app_id,
        "app_secret":      app_secret,
        "receive_id":      receive_id,
        "ai_api_token":    ai_api_token,
    }
