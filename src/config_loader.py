"""配置加载与校验模块"""

import json
import os
from pathlib import Path


def load_settings(config_dir, name, required_keys):
    """加载 JSON 配置文件并校验必填字段。

    Args:
        config_dir: 配置文件所在目录
        name: 文件名
        required_keys: [(key, description), ...] 必填字段列表

    Returns:
        解析后的 dict

    Raises:
        FileNotFoundError: 配置文件不存在
        ValueError: 必填字段缺失
    """
    file = config_dir / name
    if not file.exists():
        raise FileNotFoundError(
            f"\u914d\u7f6e\u6587\u4ef6\u4e0d\u5b58\u5728: {file}\n"
            f"\u8bf7\u590d\u5236 {name.replace('.json', '.example.json')} "
            f"\u5e76\u4fee\u6539\u4e3a {name}"
        )

    with open(file, "r", encoding="utf-8") as f:
        data = json.load(f)

    errors = []
    for key, desc in required_keys:
        if key not in data:
            errors.append(
                f"  - [{key}] {desc}\n"
                f"\u8bf7\u53c2\u8003 {name.replace('.json', '.example.json')}"
            )

    if errors:
        msg = (
            f"\u914d\u7f6e\u6587\u4ef6 {file} \u6821\u9a8c\u5931\u8d25\uff0c"
            f"\u7f3a\u5c11\u4ee5\u4e0b\u5fc5\u586b\u5b57\u6bb5\uff1a\n"
            + "\n".join(errors)
        )
        raise ValueError(msg)

    return data


def load_text(config_dir, name):
    """加载纯文本配置文件。

    Raises:
        FileNotFoundError: 文件不存在
    """
    file = config_dir / name
    if not file.exists():
        raise FileNotFoundError(
            f"\u6587\u672c\u6587\u4ef6\u4e0d\u5b58\u5728: {file}\n"
            f"\u8bf7\u590d\u5236 {name.replace('.txt', '.example.txt')} "
            f"\u5e76\u4fee\u6539\u4e3a {name}"
        )
    with open(file, "r", encoding="utf-8") as f:
        return f.read()


def load_prompt_fallback(config_dir):
    """加载降级提示词，文件不存在时返回内置默认值。"""
    try:
        return load_text(config_dir, "prompt_fallback.txt")
    except FileNotFoundError:
        return (
            "\u57fa\u4e8e\u4ee5\u4e0b\u65b0\u95fb\u64b0\u5199\u4e94\u6bb5\u5f0f Markdown \u60c5\u62a5\u7b80\u62a5"
            "\uff08\u653f\u7b56/\u6280\u672f/\u7ade\u4e89/\u5e02\u573a/\u884c\u52a8\u5efa\u8bae\uff09\uff1a\n"
            "{articles_text}"
        )


def load_all(config_dir):
    """加载全部配置文件并返回统一配置对象。

    Args:
        config_dir: config/ 目录路径

    Returns:
        dict: 包含所有配置项的字典
    """
    settings = load_settings(config_dir, "settings.json", [
        ("ceid_map",       "Google News \u56fd\u5bb6/\u8bed\u8a00\u6620\u5c04"),
        ("region_flags",   "\u5730\u533a\u56fd\u65d7 emoji \u6620\u5c04"),
        ("region_buckets", "\u5730\u533a\u5206\u7ec4\u89c4\u5219"),
        ("ai_endpoint",    "AI API \u7aef\u70b9\u5730\u5740"),
        ("ai_model",       "AI \u6a21\u578b\u540d\u79f0"),
        ("max_tokens",     "AI \u6700\u5927\u8f93\u51fa token"),
        ("temperature",    "AI \u6e29\u5ea6\u53c2\u6570"),
    ])

    sources = load_settings(config_dir, "sources.json", [
        ("queries",      "Google News \u68c0\u7d22\u8bcd\u5217\u8868"),
        ("max_articles", "\u6700\u5927\u91c7\u96c6\u6587\u7ae0\u6570\u91cf"),
    ])

    prompt_system = load_text(config_dir, "prompt_system.txt")
    prompt_user   = load_text(config_dir, "prompt_user.txt")
    prompt_fallback = load_prompt_fallback(config_dir)

    # 环境变量
    webhook_url  = os.environ.get("FEISHU_WEBHOOK_URL", "")
    feishu_secret = os.environ.get("FEISHU_SECRET", "")
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
        "webhook_url":     webhook_url,
        "feishu_secret":   feishu_secret,
        "ai_api_token":    ai_api_token,
    }
