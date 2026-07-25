#!/usr/bin/env python3
"""燃料电池每日情报自动化推送 —— 主入口

用法：
  正式推送:  python main.py
  调试预览:  DRY_RUN=1 python main.py
"""

import os, sys, time as time_module, traceback
from pathlib import Path
from datetime import datetime

# 确保 src/ 在 Python 搜索路径中
sys.path.insert(0, str(Path(__file__).parent))

from src.config_loader import load_all
from src.crawler import search_all
from src.ai_client import ai_analyze
from src.feishu_bot import (
    send_card,
    send_alert,
    split_markdown,
    build_summary_card,
    build_source_cards,
)

# ══════════════════════════════════════════════════════════════
# 防重复推送
# ══════════════════════════════════════════════════════════════
_STATE_FILE = Path(__file__).parent / ".push_state"


def _check_already_pushed(today):
    """检查当天是否已推送。"""
    try:
        if _STATE_FILE.exists():
            last = _STATE_FILE.read_text(encoding="utf-8").strip()
            return last == today
    except Exception:
        pass
    return False


def _mark_pushed(today):
    """标记当天已推送。"""
    _STATE_FILE.write_text(today, encoding="utf-8")


# ══════════════════════════════════════════════════════════════
# 推送流程
# ══════════════════════════════════════════════════════════════
def push(title, content, color, dry, cfg):
    """统一的推送/预览入口。"""
    if dry:
        print(f"\n=== {title} ({color}) ===\n{content}\n")
        return True
    return send_card(
        cfg["webhook_url"], cfg["feishu_secret"],
        title, content, color,
    )


def run():
    """主流程：配置加载 → 采集 → AI 分析 → 推送。"""
    td = datetime.now()
    today_full = td.strftime("%Y-%m-%d")
    today_short = today_full.split("-")[1]
    dry = bool(os.environ.get("DRY_RUN"))

    # ── 防重复 ──
    if not dry and _check_already_pushed(today_full):
        print(f"[SKIP] {today_full} 已推送过，跳过本次执行")
        return

    # ── 加载配置 ──
    config_dir = Path(__file__).parent / "config"
    cfg = load_all(config_dir)
    settings = cfg["settings"]

    # ── [1/3] 采集 ──
    print("[1/3] 采集资讯...")
    skip_kw = settings.get("skip_keywords")
    articles = search_all(
        cfg["sources"],
        settings["ceid_map"],
        skip_keywords=skip_kw,
    )
    print(f"  采集完成: {len(articles)} 篇")

    if not articles:
        if dry:
            print(f"\n=== 今日无新闻 ===\n{settings.get('no_news_text')}\n")
        else:
            send_card(
                cfg["webhook_url"], cfg["feishu_secret"],
                "No News",
                settings.get("no_news_text", "No fuel cell news today."),
                settings.get("no_news_card_color", "red"),
            )
        return

    # ── [2/3] AI 分析 ──
    print("[2/3] AI 分析...")
    ai_result = ai_analyze(articles, cfg)
    print(f"  分析完成 (raw={ai_result.get('raw')})")

    # ── [3/3] 推送 ──
    print("[3/3] 推送飞书卡片...")

    # Card 1: 摘要
    st, sc, scol = build_summary_card(ai_result, today_full, settings)
    push(st, sc, scol, dry, cfg)
    print("  [OK] 摘要卡片")

    # Card 2+: 报告正文
    body = (ai_result.get("text", "") if ai_result.get("raw")
            else ai_result.get("sections", ""))
    chunks = split_markdown(body, settings.get("card_char_limit", 4500))
    for idx, chunk in enumerate(chunks, 1):
        title = (
            f"Fuel Cell Report {idx} - {today_full}"
            if len(chunks) > 1
            else f"Fuel Cell Report - {today_full}"
        )
        push(title, chunk, settings.get("report_card_color", "green"), dry, cfg)
        print(f"  [OK] {title}")

    # Cards: 信源列表
    for title, content, color in build_source_cards(articles, today_short, settings):
        push(title, content, color, dry, cfg)
        print(f"  [OK] {title}")

    # 标记已推送
    if not dry:
        _mark_pushed(today_full)

    print("Done!")


# ══════════════════════════════════════════════════════════════
# 全局异常捕获 — 崩溃时自动推送飞书故障告警
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        run()
    except Exception:
        tb = traceback.format_exc()
        print(f"[FATAL] {tb}")

        # 尝试推送故障告警（不影响异常抛出）
        try:
            config_dir = Path(__file__).parent / "config"
            cfg = load_all(config_dir)
            if cfg["webhook_url"] and cfg["feishu_secret"]:
                send_alert(
                    cfg["webhook_url"], cfg["feishu_secret"],
                    f"脚本运行异常:\n```\n{tb[-1500:]}\n```",
                )
        except Exception:
            pass

        sys.exit(1)
