"""AI 分析模块 —— 调用大模型生成情报简报"""

import json

from .utils import http_post_json


def ai_analyze(articles, cfg, _print=print):
    """AI 智能分析：优先 JSON 结构化输出，失败降级为纯文本。

    Args:
        articles: 文章列表
        cfg: 配置对象（含 settings/prompts/tokens 等）
        _print: 日志输出函数

    Returns:
        dict: {
            "raw": bool,              # True 表示降级为纯文本
            "headline": str,          # 摘要标题（raw=False）
            "key_points": list[str],  # 核心要点（raw=False）
            "sections": str,          # Markdown 正文（raw=False）
            "text": str,              # 降级纯文本（raw=True）
        }
    """
    settings     = cfg["settings"]
    prompt_sys   = cfg["prompt_system"]
    prompt_user  = cfg["prompt_user"]
    prompt_fb    = cfg["prompt_fallback"]
    ai_token     = cfg["ai_api_token"]
    region_flags = settings["region_flags"]

    # 构建文章文本
    articles_text = ""
    for i, a in enumerate(articles):
        flag = region_flags.get(a["region"], "")
        articles_text += f"\n{i+1}. {flag} {a['title']} | {a['source']}"

    if not ai_token:
        return {"raw": True, "text": "AI_API_TOKEN 未设置，请检查 GitHub Secrets。"}

    # ── 尝试 JSON 结构化输出 ──
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

        # 字段缺失自动填充默认值
        return {
            "raw":       False,
            "headline":  data.get("headline", ""),
            "key_points": data.get("key_points", []),
            "sections":  data.get("sections", ""),
        }

    except Exception as e:
        _print(f"  [WARN] AI JSON 结构化失败: {e}，降级为纯文本模式")

        # ── 降级：纯 Markdown 输出 ──
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
