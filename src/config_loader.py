"""
================================================================================
配置加载与校验模块 (config_loader.py) 
================================================================================
职责：统一管理所有配置文件的读取、校验和合并，向其他模块提供单一配置入口。

新增：report_config.json 加载逻辑（v3.0）
  - load_report_config() 加载数据驱动的报告配置
  - 不存在时自动回退到 .example 模板
  - 支持用户通过 JSON 定义追踪品种、数据源、新闻话题

设计要点：
  1. 自动回退：正式配置文件不存在时，自动使用 .example 模板
  2. 前置校验：加载后检查必填字段，缺失项输出中文提示
  3. 环境变量隔离：密钥类信息一律从环境变量读取
================================================================================
"""

import json
import os
from .env_vars import (ENV_FEISHU_APP_ID, ENV_FEISHU_APP_SECRET, ENV_FEISHU_RECEIVE_ID, ENV_AI_TOKEN, ENV_AI_TOKEN_FALLBACK)
from pathlib import Path


def _find_config(config_dir, name):
    """查找配置文件：优先正式文件，不存在则回退到 .example 模板。"""
    real = config_dir / name
    if real.exists():
        return real

    example = config_dir / name.replace(".json", ".example.json").replace(".txt", ".example.txt")
    if example.exists():
        print(f"  [INFO] {name} 不存在，使用模板 {example.name}")
        return example

    raise FileNotFoundError(
        f"配置文件不存在: {real}\n请创建该文件或确保模板 {example.name} 存在"
    )


def load_json(config_dir, name, required_keys=None):
    """加载 JSON 配置文件并校验必填字段。"""
    file = _find_config(config_dir, name)
    with open(file, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    if required_keys:
        errors = []
        for key, desc in required_keys:
            if key not in data:
                errors.append(f"  - [{key}] {desc}")
        if errors:
            raise ValueError(
                f"配置文件 {file} 校验失败，缺少以下必填字段：\n" + "\n".join(errors)
            )
    return data


def load_text(config_dir, name):
    """加载纯文本配置文件。"""
    file = _find_config(config_dir, name)
    with open(file, "r", encoding="utf-8-sig") as f:
        return f.read()


def load_prompt_fallback(config_dir):
    """加载降级提示词。"""
    try:
        return load_text(config_dir, "prompt_fallback.txt")
    except FileNotFoundError:
        return (
            "基于以下新闻撰写五段式 Markdown 情报简报"
            "（政策/技术/竞争/市场/行动建议）：\n"
            "{articles_text}"
        )


# ================================================================
# 新增：报告配置加载
# ================================================================

def load_report_config(config_dir):
    """加载 report_config.json —— 报告的数据模型定义。

    这是 v3.0 的核心改进：增删品种、换行业只需编辑此 JSON 文件。

    返回的字典包含：
      - report:      报告元数据（标题、行业、受众、配色等）
      - data_items:  数据采集项列表（每个 item 定义名称、数据源、品种代码等）
      - news:        新闻采集配置（话题关键词、过滤词）
      - ai:          AI 模型配置
      - regions:     地区/国旗映射

    Args:
        config_dir: config/ 目录的 Path 对象

    Returns:
        dict: 报告配置
    """
    return load_json(config_dir, "report_config.json", [
        ("data_items", "市场数据采集项列表"),
        ("news",        "新闻采集配置"),
        ("report",      "报告元数据"),
    ])


# ================================================================
# 全量加载入口
# ================================================================

def load_all(config_dir):
    """加载全部配置文件，返回统一的配置对象供其他模块使用。"""
    # ── JSON 配置 ──
    settings = load_json(config_dir, "settings.json", [
        ("ai_endpoint", "AI API 端点地址"),
        ("ai_model",    "AI 模型名称"),
        ("max_tokens",  "AI 最大输出 token"),
        ("temperature", "AI 温度参数"),
    ])

    sources = load_json(config_dir, "sources.json", [
        ("queries",      "Google News 检索词列表"),
        ("max_articles", "最大采集文章数量"),
    ])

    # ── 新增：报告配置（数据驱动） ──
    report_cfg = load_report_config(config_dir)

    # ── 纯文本提示词 ──
    prompt_system   = load_text(config_dir, "prompt_system.txt")
    prompt_user     = load_text(config_dir, "prompt_user.txt")
    prompt_fallback = load_prompt_fallback(config_dir)

    # ── 环境变量密钥 ──
    app_id     = os.environ.get(ENV_FEISHU_APP_ID, "")
    app_secret = os.environ.get(ENV_FEISHU_APP_SECRET, "")
    receive_id = os.environ.get(ENV_FEISHU_RECEIVE_ID, "")

    ai_api_token = (
        os.environ.get(ENV_AI_TOKEN)
        or os.environ.get(ENV_AI_TOKEN_FALLBACK, "")
    )

    # ── 合并：report_config 中的设置覆盖旧 settings ──
    merged_settings = dict(settings)
    merged_settings.update({
        "report_title":        report_cfg["report"].get("title", "每日情报报告"),
        "card_char_limit":     report_cfg["report"].get("card_char_limit", 4500),
        "summary_card_color":  report_cfg["report"].get("summary_card_color", "blue"),
        "report_card_color":   report_cfg["report"].get("report_card_color", "green"),
        "kpi_card_color":      report_cfg["report"].get("kpi_card_color", "blue"),
        "chart_card_color":    report_cfg["report"].get("chart_card_color", "wathet"),
        "no_news_text":        report_cfg["report"].get("no_news_text", "今日暂无相关新闻。"),
        "skip_keywords":       report_cfg["news"].get("skip_keywords", []),
        "news_topics":         report_cfg["news"].get("topics", []),
        "region_flags":        {k: v.get("flag", "") for k, v in report_cfg.get("regions", {}).items()},
        "ceid_map":            settings.get("ceid_map", {}),
        "region_buckets":      report_cfg.get("region_buckets", {
            "中国": ["CN"], "美洲": ["US", "CL"], "其他": ["GB", "AU", "GLOBAL"],
        }),
    })

    return {
        "settings":        merged_settings,
        "sources":         sources,
        "report_config":   report_cfg,
        "data_items":      report_cfg.get("data_items", []),
        "prompt_system":   prompt_system,
        "prompt_user":     prompt_user,
        "prompt_fallback": prompt_fallback,
        "app_id":          app_id,
        "app_secret":      app_secret,
        "receive_id":      receive_id,
        "ai_api_token":    ai_api_token,
    }
