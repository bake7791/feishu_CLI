"""
================================================================================
配置加载与校验模块 (config_loader.py)
================================================================================
职责：统一管理所有配置文件的读取、校验和合并，向其他模块提供单一配置入口。

设计要点：
  1. 自动回退：正式配置文件不存在时，自动使用 .example 模板
     （这样 GitHub Actions 首次运行无需手动 cp 文件）
  2. 前置校验：加载 settings.json 和 sources.json 后立即检查必填字段，
     缺失项输出中文提示，避免运行时才报 KeyError
  3. 环境变量隔离：密钥类信息（App ID/Secret/Token）一律从环境变量读取，
     不写入配置文件，防止泄露

修改指南：
  - 新增配置项：在 settings.example.json 中添加，然后在本文件的
    load_all() 函数的 required_keys 列表中添加对应的 (key, description)
  - 新增配置文件：仿照 load_settings/load_text 的模式新增加载函数
================================================================================
"""

import json
import os
from pathlib import Path


def _find_config(config_dir, name):
    """查找配置文件：优先正式文件，不存在则回退到 .example 模板。
    
    这是 v2.0 新增的核心改进，使得项目开箱即用：
    Fork 后不需要手动 cp 文件，可直接在 GitHub Actions 中运行。
    
    Args:
        config_dir: config/ 目录路径
        name:       目标文件名（如 "settings.json"）
    
    Returns:
        Path: 实际使用的文件路径
    
    Raises:
        FileNotFoundError: 正式文件和模板文件都不存在
    """
    real = config_dir / name
    if real.exists():
        return real
    
    # 根据扩展名构造对应的 .example 文件名
    example = config_dir / name.replace(".json", ".example.json").replace(".txt", ".example.txt")
    if example.exists():
        print(f"  [INFO] {name} 不存在，使用模板 {example.name}")
        return example
    
    raise FileNotFoundError(
        f"配置文件不存在: {real}\n请创建该文件或确保模板 {example.name} 存在"
    )


def load_settings(config_dir, name, required_keys):
    """加载 JSON 配置文件并校验必填字段。
    
    Args:
        config_dir:    配置文件所在目录
        name:          文件名（如 "settings.json"）
        required_keys: [(key, description), ...] 必填字段列表，
                       用于生成中文错误提示
    
    Returns:
        dict: 解析后的配置字典
    
    Raises:
        FileNotFoundError: 文件不存在且无模板
        ValueError:        必填字段缺失
    """
    file = _find_config(config_dir, name)
    # 注意：使用 utf-8-sig 编码以兼容 Windows 记事本保存的 UTF-8 BOM 文件
    with open(file, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    # 收集缺失的必填字段
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
    """加载纯文本配置文件（如提示词模板）。
    
    Args:
        config_dir: 配置文件所在目录
        name:       文件名（如 "prompt_system.txt"）
    
    Returns:
        str: 文件内容
    
    Raises:
        FileNotFoundError: 文件不存在且无模板
    """
    file = _find_config(config_dir, name)
    with open(file, "r", encoding="utf-8-sig") as f:
        return f.read()


def load_prompt_fallback(config_dir):
    """加载降级提示词。与 load_text 的区别在于：
    如果文件不存在，返回内置默认值而不是报错。
    
    降级提示词用于 AI 的 JSON 结构化输出失败时的备用纯文本模式，
    这个场景即使没有配置也应该能工作。
    """
    try:
        return load_text(config_dir, "prompt_fallback.txt")
    except FileNotFoundError:
        return (
            "基于以下新闻撰写五段式 Markdown 情报简报"
            "（政策/技术/竞争/市场/行动建议）：\n"
            "{articles_text}"
        )


def load_all(config_dir):
    """加载全部配置文件，返回统一的配置对象供其他模块使用。
    
    这是项目启动时的唯一配置入口，调用一次即可拿到所有配置。
    返回的字典包含以下几类数据：
      - settings:  业务参数（AI 端点、卡片样式、地区映射等）
      - sources:   信源参数（检索词、RSS 地址、最大文章数）
      - prompts:   AI 提示词模板
      - 密钥信息:   从环境变量读取（不落盘、不进 Git）
    
    Args:
        config_dir: config/ 目录的 Path 对象
    
    Returns:
        dict: 包含所有配置项的统一字典
    """
    # ── 加载 JSON 配置文件 ──
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

    # ── 加载纯文本提示词 ──
    prompt_system   = load_text(config_dir, "prompt_system.txt")
    prompt_user     = load_text(config_dir, "prompt_user.txt")
    prompt_fallback = load_prompt_fallback(config_dir)

    # ── 从环境变量读取密钥（绝不写入文件） ──
    app_id     = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    receive_id = os.environ.get("FEISHU_RECEIVE_ID", "")

    # AI Token：优先使用 AI_API_TOKEN，兼容旧的 GITHUB_TOKEN 命名
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
