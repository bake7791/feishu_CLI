#!/usr/bin/env python3
"""
================================================================================
铜及预焙阳极每日情报自动化推送 —— 主入口 (main.py)
================================================================================
这是整个项目的唯一入口文件，负责串联所有模块完成每日情报的采集、分析和推送。

运行方式：
  正式推送：  python main.py
  调试预览：  DRY_RUN=1 python main.py    （仅打印不推送，用于本地开发调试）

执行流程：
  config_loader → 加载配置
  crawler       → 采集新闻（Google News + 自定义 RSS）
  ai_client     → AI 分析（生成 8 模块决策级报告）
  feishu_bot    → 推送飞书卡片（摘要 + 报告 + 信源列表）

防重复机制：
  每次成功推送后在 .push_state 文件中记录日期，同一天重复触发时自动跳过，
  避免 GitHub Actions 手动重跑导致飞书群刷屏。

异常处理：
  顶层 try/except 捕获全部异常，崩溃时自动推送飞书故障告警，不静默失败。

修改指南：
  - 本文件应保持极简，只负责流程串联，不包含业务逻辑
  - 如需修改采集策略 → src/crawler.py
  - 如需修改 AI 分析逻辑 → src/ai_client.py + config/prompt_system.txt
  - 如需修改推送方式 → src/feishu_bot.py
  - 如需修改配置 → config/ 目录下的各配置文件
================================================================================
"""

import os, sys, traceback
from pathlib import Path
from datetime import datetime

# 确保 src/ 目录在 Python 搜索路径中（支持从任意目录运行）
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

# 修复 Windows 控制台 emoji 编码问题（仅影响本地 dry run 打印，不影响飞书推送）
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ══════════════════════════════════════════════════════════════
# 防重复推送机制
# ══════════════════════════════════════════════════════════════

_STATE_FILE = Path(__file__).parent / ".push_state"


def _check_already_pushed(today):
    """检查今天是否已经推送过，避免重复推送。
    
    原理：每次成功推送后在项目根目录写入日期字符串（如 "2026-07-26"）。
    下次运行时先读取对比，相同则跳过。
    此文件已在 .gitignore 中排除，不会提交到仓库。
    """
    try:
        if _STATE_FILE.exists():
            return _STATE_FILE.read_text(encoding="utf-8").strip() == today
    except Exception:
        pass
    return False


def _mark_pushed(today):
    """标记今天已推送。"""
    _STATE_FILE.write_text(today, encoding="utf-8")


# ══════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════

def run():
    """执行一次完整的情报推送流程。
    
    步骤：
      1. 防重复检查
      2. 加载所有配置
      3. 采集信源 → 去重排序
      4. AI 分析 → 生成报告
      5. 推送飞书卡片（摘要 + 正文 + 信源列表）
    """
    td = datetime.now()
    today_full  = td.strftime("%Y-%m-%d")       # 完整日期：2026-07-26
    today_short = today_full.split("-")[1]      # 月份：07（用于信源卡片标题）
    dry = bool(os.environ.get("DRY_RUN"))       # DRY_RUN 模式：只打印不推送

    # ── 防重复：今天已经推过则跳过 ──
    if not dry and _check_already_pushed(today_full):
        print(f"[SKIP] {today_full} 已推送过，跳过本次执行")
        return

    # ── 加载配置 ──
    config_dir  = Path(__file__).parent / "config"
    cfg         = load_all(config_dir)
    settings    = cfg["settings"]
    app_id      = cfg["app_id"]
    app_secret  = cfg["app_secret"]
    receive_id  = cfg["receive_id"]
    report_title = settings.get("report_title", "每日情报")  # 卡片标题（可配置）

    # ══════════════════════════════════════════════════════
    # [1/3] 采集新闻
    # ══════════════════════════════════════════════════════
    print("[1/3] 采集资讯...")
    articles = search_all(
        cfg["sources"],
        settings["ceid_map"],
        skip_keywords=settings.get("skip_keywords"),
    )
    print(f"  采集完成: {len(articles)} 篇")

    # 无新闻时的处理：推送空消息或预览提示
    if not articles:
        if dry:
            print(f"\n=== 今日无新闻 ===\n{settings.get('no_news_text')}\n")
        else:
            send_card(app_id, app_secret, receive_id,
                      "No News",
                      settings.get("no_news_text", ""),
                      settings.get("no_news_card_color", "red"))
        return

    # ══════════════════════════════════════════════════════
    # [2/3] AI 分析
    # ══════════════════════════════════════════════════════
    print("[2/3] AI 分析...")
    ai_result = ai_analyze(articles, cfg)
    print(f"  分析完成 (raw={ai_result.get('raw')})")

    # ══════════════════════════════════════════════════════
    # [3/3] 推送飞书卡片
    # ══════════════════════════════════════════════════════
    print("[3/3] 推送飞书卡片...")

    card_limit = settings.get("card_char_limit", 4500)  # 单卡片最大字符数

    # Card 1: 摘要卡片（核心结论 + 关键要点）
    st, sc, scol = build_summary_card(ai_result, today_full, settings)
    if dry:
        print(f"\n=== {st} ({scol}) ===\n{sc}\n")
    else:
        send_card(app_id, app_secret, receive_id, st, sc, scol)
    print("  [OK] 摘要卡片")

    # Card 2+: 报告正文（8 模块 Markdown，可能拆成多张卡片）
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

    # Cards: 信源列表（按地区分组，可能拆成多张）
    for title, content, color in build_source_cards(articles, today_short, settings):
        if dry:
            print(f"\n=== {title} ({color}) ===\n{content}\n")
        else:
            send_card(app_id, app_secret, receive_id, title, content, color)
        print(f"  [OK] {title}")

    # ── 标记已推送 ──
    if not dry:
        _mark_pushed(today_full)

    print("Done!")


# ══════════════════════════════════════════════════════════════
# 全局异常捕获 & 飞书故障告警
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        run()
    except Exception:
        # 出现任何未预料的异常 → 打印堆栈 + 尝试推送飞书告警
        tb = traceback.format_exc()
        print(f"[FATAL] {tb}")

        try:
            config_dir = Path(__file__).parent / "config"
            cfg = load_all(config_dir)
            if cfg["app_id"] and cfg["app_secret"] and cfg["receive_id"]:
                send_alert(cfg["app_id"], cfg["app_secret"], cfg["receive_id"],
                           f"脚本运行异常:\n```\n{tb[-1500:]}\n```")
        except Exception:
            pass  # 告警推送失败也不影响异常抛出

        sys.exit(1)  # 返回非零退出码，让 GitHub Actions 感知到失败
