"""
================================================================================
AI 分析模块 (ai_client.py) — 增强版
================================================================================
职责：调用大语言模型对新闻进行智能分析，生成结构化情报简报。

增强点（v2.0）：
  - 新增 sentiment_index：综合情绪指数（-10 偏空 ~ +10 偏多）
  - 新增 news_sentiments：每条重要新闻的情绪打分
  - 市场数据不经过 AI，直接由 data_fetcher 渲染到卡片

工作流程：
  1. 拼接新闻标题为文本
  2. 发送给 LLM，要求 JSON 格式输出
  3. JSON 解析失败 → 降级为纯文本模式
  4. 降级也失败 → 返回错误提示（不崩溃）
================================================================================
"""

import json

from .utils import http_post_json


def _format_sections(sections_data):
    """将 AI 返回的 sections 字段统一转换为 Markdown 字符串。"""
    if isinstance(sections_data, str):
        return sections_data
    if not isinstance(sections_data, dict):
        return str(sections_data)

    parts = []
    for title, content in sections_data.items():
        parts.append(f"## {title}\n\n{content}")
    return "\n\n".join(parts)


def ai_analyze(articles, cfg, _print=print):
    """AI 智能分析主函数。

    先尝试 JSON 结构化模式获取 headline/key_points/sections/sentiment，
    失败则降级为纯文本 Markdown 模式。

    Returns:
        dict: {
            "raw":              bool,
            "headline":         str,
            "key_points":       list[str],
            "sections":         str,
            "sentiment_index":  float | None,   # -10 ~ +10
            "news_sentiments":  list[dict],     # [{title, sentiment, impact}]
            "text":             str,            # 降级纯文本
        }
    """
    settings = cfg["settings"]
    prompt_sys = cfg["prompt_system"]
    prompt_user = cfg["prompt_user"]
    prompt_fb = cfg["prompt_fallback"]
    ai_token = cfg["ai_api_token"]
    region_flags = settings.get("region_flags", {})

    articles_text = ""
    for i, a in enumerate(articles):
        flag = region_flags.get(a["region"], "")
        articles_text += f"\n{i+1}. {flag} {a['title']} | {a['source']}"

    if not ai_token:
        return {"raw": True, "text": "AI_API_TOKEN 未设置，请检查 GitHub Secrets。"}

    # -- 模式 1：JSON 结构化输出 --
    try:
        result = http_post_json(settings["ai_endpoint"], {
            "model": settings["ai_model"],
            "messages": [
                {"role": "system", "content": prompt_sys},
                {"role": "user", "content": prompt_user.format(
                    article_count=len(articles),
                    articles_text=articles_text,
                )},
            ],
            "max_tokens": settings["max_tokens"],
            "temperature": settings["temperature"],
            "response_format": {"type": "json_object"},
        }, headers={"Authorization": f"Bearer {ai_token}"})

        content = result["choices"][0]["message"]["content"]
        data = json.loads(content)

        return {
            "raw": False,
            "headline": data.get("headline", ""),
            "key_points": data.get("key_points", []),
            "sections": _format_sections(data.get("sections", {})),
            "sentiment_index": data.get("sentiment_index"),
            "news_sentiments": data.get("news_sentiments", []),
        }

    except Exception as e:
        _print(f"  [WARN] AI JSON 结构化失败: {e}，降级为纯文本模式")

    # -- 模式 2：纯文本降级 --
    try:
        fallback_content = prompt_fb.format(articles_text=articles_text)
        result = http_post_json(settings["ai_endpoint"], {
            "model": settings["ai_model"],
            "messages": [
                {"role": "system", "content": prompt_sys},
                {"role": "user", "content": fallback_content},
            ],
            "max_tokens": 3000,
            "temperature": settings["temperature"],
        }, headers={"Authorization": f"Bearer {ai_token}"})
        return {"raw": True, "text": result["choices"][0]["message"]["content"]}

    except Exception as e2:
        return {"raw": True, "text": f"AI 分析失败: {e2}"}
