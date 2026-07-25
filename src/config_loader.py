"""配置加载与校验模块 —— 自动回退到 .example 模板"""

import json
import os
from pathlib import Path


def _find_config(config_dir, name):
    """查找配置文件，优先正式文件，不存在则回退到 .example 模板。"""
    real = config_dir / name
    if real.exists():
        return real
    example = config_dir / name.replace(".json", ".example.json").replace(".txt", ".example.txt")
    if example.exists():
        print(f"  [INFO] {name} 不存在，使用模板 {example.name}")
        return example
    raise FileNotFoundError(f"配置文件不存在: {real}\n请创建该文件或确保模板 {example.name} 存在")


def load_settings(config_dir, name, required_keys):
    file = _find_config(config_dir, name)
    with open(file, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    errors = []
    for key, desc in required_keys:
        if key not in data:
            errors.append(f"  - [{key}] {desc}")

    if errors:
        msg = (
            f"配置文件 {file} 校验失败，缺少以下必填字段：\n"
            + "\n".join(errors)
        )
        raise ValueError(msg)

    return data


def load_text(config_dir, name):
    file = _find_config(config_dir, name)
    with open(file, "r", encoding="utf-8-sig") as f:
        return f.read()


def load_prompt_fallback(config_dir):
    try:
        return load_text(config_dir, "prompt_fallback.txt")
    except FileNotFoundError:
        return (
            "基于以下新闻撰写五段式 Markdown 情报简报"
            "（政策/技术/竞争/市场/行动建议）：\n"
            "{articles_text}"
        )


def load_all(config_dir):
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

    app_id     = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    receive_id = os.environ.get("FEISHU_RECEIVE_ID", "")

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
