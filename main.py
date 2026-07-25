#!/usr/bin/env python3
"""铜及预焙阳极每日情报自动化推送 —— 主入口（企业自建应用机器人）

用法：
  正式推送:  python main.py
  调试预览:  DRY_RUN=1 python main.py
"""

import os, sys, traceback
from pathlib import Path
from datetime import datetime

# 修复 Windows 控制台 emoji 编码问题（仅影响本地 dry run，不影响飞书推送）
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

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

_STATE_FILE = Path(__file__).parent / ".push_state"


def _check_already_pushed(today):
    try:
        if _STATE_FILE.exists():
            return _STATE_FILE.read_text(encoding="utf-8").strip() == today
    except Exception:
        pass
    return False


def _mark_pushed(today):
    _STATE_FILE.write_text(today, encoding="utf-8")


def run():
    td = datetime.now()
    today_full = td.strftime("%Y-%m-%d")
    today_short = today_full.split("-")[1]
    dry = bool(os.environ.get("DRY_RUN"))

    if not dry and _check_already_pushed(today_full):
        print(f"[SKIP] {today_full} 已推送过，跳过本次执行")
        return

    config_dir = Path(__file__).parent / "config"
    cfg = load_all(config_dir)
    settings = cfg["settings"]
    app_id     = cfg["app_id"]
    app_secret = cfg["app_secret"]
    receive_id = cfg["receive_id"]
    report_title = settings.get("report_title", "每日情报")

    # ── [1/3] 采集 ──
    print("[1/3] 采集资讯...")
    articles = search_all(
        cfg["sources"], settings["ceid_map"],
        skip_keywords=settings.get("skip_keywords"),
    )
    print(f"  采集完成: {len(articles)} 篇")

    if not articles:
        if dry:
            print(f"\n=== 今日无新闻 ===\n{settings.get('no_news_text')}\n")
        else:
            send_card(app_id, app_secret, receive_id,
                      "No News", settings.get("no_news_text", ""),
                      settings.get("no_news_card_color", "red"))
        return

    # ── [2/3] AI 分析 ──
    print("[2/3] AI 分析...")
    ai_result = ai_analyze(articles, cfg)
    print(f"  分析完成 (raw={ai_result.get('raw')})")

    # ── [3/3] 推送 ──
    print("[3/3] 推送飞书卡片...")

    card_limit = settings.get("card_char_limit", 4500)

    # Card 1: 摘要
    st, sc, scol = build_summary_card(ai_result, today_full, settings)
    if dry:
        print(f"\n=== {st} ({scol}) ===\n{sc}\n")
    else:
        send_card(app_id, app_secret, receive_id, st, sc, scol)
    print("  [OK] 摘要卡片")

    # Card 2+: 报告正文
    body = (ai_result.get("text", "") if ai_result.get("raw")
            else ai_result.get("sections", ""))
    chunks = split_markdown(body, card_limit)
    for idx, chunk in enumerate(chunks, 1):
        title = (f"{report_title} {idx} - {today_full}"
                 if len(chunks) > 1
                 else f"{report_title} - {today_full}")
        if dry:
            print(f"\n=== {title} ===\n{chunk}\n")
        else:
            send_card(app_id, app_secret, receive_id, title, chunk,
                      settings.get("report_card_color", "green"))
        print(f"  [OK] {title}")

    # Cards: 信源列表
    for title, content, color in build_source_cards(articles, today_short, settings):
        if dry:
            print(f"\n=== {title} ({color}) ===\n{content}\n")
        else:
            send_card(app_id, app_secret, receive_id, title, content, color)
        print(f"  [OK] {title}")

    if not dry:
        _mark_pushed(today_full)

    print("Done!")


if __name__ == "__main__":
    try:
        run()
    except Exception:
        tb = traceback.format_exc()
        print(f"[FATAL] {tb}")
        try:
            config_dir = Path(__file__).parent / "config"
            cfg = load_all(config_dir)
            if cfg["app_id"] and cfg["app_secret"] and cfg["receive_id"]:
                send_alert(cfg["app_id"], cfg["app_secret"], cfg["receive_id"],
                           f"脚本运行异常:\n```\n{tb[-1500:]}\n```")
        except Exception:
            pass
        sys.exit(1)
