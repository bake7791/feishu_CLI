"""AI 分析模块 —— 调用大模型生成情报简报"""

import json

from .utils import http_post_json


def _format_sections(sections_data):
    """将 sections dict 或字符串统一转换为 Markdown 格式。"""
    if isinstance(sections_data, str):
        return sections_data
    if not isinstance(sections_data, dict):
        return str(sections_data)
    parts = []
    for title, content in sections_data.items():
        parts.append(f"## {title}\n\n{content}")
    return "\n\n".join(parts)


def ai_analyze(articles, cfg, _print=print):
    """AI 智能分析：优先 JSON 结构化输出，失败降级为纯文本。"""
    settings     = cfg["settings"]
    prompt_sys   = cfg["prompt_system"]
    prompt_user  = cfg["prompt_user"]
    prompt_fb    = cfg["prompt_fallback"]
    ai_token     = cfg["ai_api_token"]
    region_flags = settings["region_flags"]

    articles_text = ""
    for i, a in enumerate(articles):
        flag = region_flags.get(a["region"], "")
        articles_text += f"\n{i+1}. {flag} {a['title']} | {a['source']}"

    if not ai_token:
        return {"raw": True, "text": "AI_API_TOKEN 未设置，请检查 GitHub Secrets。"}

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
            "raw":        False,
            "headline":   data.get("headline", ""),
            "key_points": data.get("key_points", []),
            "sections":   _format_sections(data.get("sections", {})),
        }

    except Exception as e:
        _print(f"  [WARN] AI JSON 结构化失败: {e}，降级为纯文本模式")

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
