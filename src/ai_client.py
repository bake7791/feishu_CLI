"""
================================================================================
AI 分析模块 (ai_client.py)
================================================================================
职责：调用大语言模型（默认 GitHub Models 免费 GPT-4o）对新闻进行智能分析，
     生成结构化的情报简报。

工作流程：
  1. 拼接 80 篇新闻标题为文本
  2. 发送给 LLM，要求 JSON 格式输出（headline + key_points + sections）
  3. 如果 JSON 解析失败 → 自动降级为纯文本模式（使用 fallback 提示词）
  4. 如果降级也失败 → 返回错误提示（不崩溃）

设计要点：
  - 双模式策略：JSON 结构化（优先）→ 纯文本降级（保底）
  - _format_sections() 兼容 dict 和 str 两种 AI 返回格式
  - 所有错误都有降级路径，绝不因 AI 异常导致整条流水线崩溃

修改指南：
  - 切换 AI 模型：修改 config/settings.json 中的 ai_endpoint 和 ai_model
  - 调整输出结构：编辑 config/prompt_system.txt
  - 调整温度/长度：修改 settings.json 中的 temperature 和 max_tokens
================================================================================
"""

import json

from .utils import http_post_json


def _format_sections(sections_data):
    """将 AI 返回的 sections 字段统一转换为 Markdown 字符串。
    
    背景：AI 有时返回 dict（如 {"今日核心速览": "..."}），
    有时返回字符串。此函数自动适配两种格式。
    
    Args:
        sections_data: AI 返回的 sections 字段，可能是 dict 或 str
    
    Returns:
        str: 格式化后的 Markdown 文本（每节以 ## 开头）
    """
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
    
    先尝试 JSON 结构化模式获取 headline/key_points/sections，
    失败则降级为纯文本 Markdown 模式。
    
    Args:
        articles: 文章列表（每篇含 title/url/source/date/region）
        cfg:      配置对象（含 settings/prompts/tokens 等）
        _print:   日志输出函数
    
    Returns:
        dict: {
            "raw":       bool,         # True = 降级纯文本模式
            "headline":  str,          # 摘要标题（raw=False 时有效）
            "key_points": list[str],   # 核心要点列表（raw=False 时有效）
            "sections":  str,          # Markdown 正文（raw=False 时有效）
            "text":      str,          # 降级纯文本（raw=True 时有效）
        }
    """
    settings     = cfg["settings"]
    prompt_sys   = cfg["prompt_system"]
    prompt_user  = cfg["prompt_user"]
    prompt_fb    = cfg["prompt_fallback"]
    ai_token     = cfg["ai_api_token"]
    region_flags = settings.get("region_flags", {})

    # ── 拼接文章文本 ──
    # 格式："1. 🇺🇸 Copper Price Rises... | SMM"
    articles_text = ""
    for i, a in enumerate(articles):
        flag = region_flags.get(a["region"], "")
        articles_text += f"\n{i+1}. {flag} {a['title']} | {a['source']}"

    # ── Token 未设置时的处理 ──
    if not ai_token:
        return {"raw": True, "text": "AI_API_TOKEN 未设置，请检查 GitHub Secrets。"}

    # ── 模式 1：JSON 结构化输出（优先） ──
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
            "max_tokens":        settings["max_tokens"],
            "temperature":       settings["temperature"],
            "response_format":   {"type": "json_object"},  # 要求 LLM 返回 JSON
        }, headers={"Authorization": f"Bearer {ai_token}"})

        content = result["choices"][0]["message"]["content"]
        data = json.loads(content)

        # 字段缺失时自动填充默认值，不因缺失字段而崩溃
        return {
            "raw":        False,
            "headline":   data.get("headline", ""),
            "key_points": data.get("key_points", []),
            "sections":   _format_sections(data.get("sections", {})),
        }

    except Exception as e:
        _print(f"  [WARN] AI JSON 结构化失败: {e}，降级为纯文本模式")

    # ── 模式 2：纯文本降级（保底） ──
    try:
        fallback_content = prompt_fb.format(articles_text=articles_text)
        result = http_post_json(settings["ai_endpoint"], {
            "model": settings["ai_model"],
            "messages": [
                {"role": "system", "content": prompt_sys},
                {"role": "user", "content": fallback_content},
            ],
            "max_tokens":  3000,
            "temperature": settings["temperature"],
        }, headers={"Authorization": f"Bearer {ai_token}"})
        return {"raw": True, "text": result["choices"][0]["message"]["content"]}

    except Exception as e2:
        # 两次都失败 → 返回错误提示（不崩溃，让主流程继续）
        return {"raw": True, "text": f"AI 分析失败: {e2}"}
