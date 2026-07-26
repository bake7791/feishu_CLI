#!/usr/bin/env python3
"""
================================================================================
铜及预焙阳极每日情报自动化推送 —— 主入口 (main.py) 增强版
================================================================================
企业自建应用增强版流水线：
  1. 采集新闻（Google News + RSS）
  2. 采集量化数据（期货价格 + 宏观指标）  ← 新增
  3. AI 分析（8模块报告 + 情绪量化）       ← 增强
  4. 渲染图表（价格趋势 + 涨跌幅柱状图）   ← 新增
  5. 推送飞书卡片：
     - 摘要卡片（含情绪指数）
     - KPI 看板卡片（column_set 多列）     ← 新增
     - 图表卡片（img 嵌入 PNG）            ← 新增
     - 报告正文卡片（8模块 Markdown）
     - 信源列表卡片（按地区分组）

运行方式：
  正式推送：  python main.py
  调试预览：  DRY_RUN=1 python main.py
================================================================================
"""

import os
import sys
import traceback
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from src.config_loader import load_all
from src.crawler import search_all
from src.ai_client import ai_analyze
from src.feishu_bot import (
    send_card,
    send_alert,
    send_elements_card,
    split_markdown,
    build_summary_card,
    build_source_cards,
    build_kpi_elements,
    build_data_table,
    build_chart_elements,
)

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


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
    app_id = cfg["app_id"]
    app_secret = cfg["app_secret"]
    receive_id = cfg["receive_id"]
    report_title = settings.get("report_title", "每日情报")

    data_items = cfg.get("data_items", [])
    enable_data = settings.get("enable_market_data", True)
    enable_charts = settings.get("enable_charts", True)

    # ============================================================
    # [1/5] 采集新闻
    # ============================================================
    print("[1/5] 采集资讯...")
    articles = search_all(
        cfg["sources"],
        settings["ceid_map"],
        skip_keywords=settings.get("skip_keywords"),
    )
    print(f"  采集完成: {len(articles)} 篇")

    if not articles:
        if dry:
            print(f"\n=== 今日无新闻 ===\n{settings.get('no_news_text')}\n")
        else:
            send_card(app_id, app_secret, receive_id, "No News",
                      settings.get("no_news_text", ""),
                      settings.get("no_news_card_color", "red"))
        return

    # ============================================================
    # [2/5] 采集量化数据
    # ============================================================
    market_data = None
    if enable_data:
        print("[2/5] 采集量化数据...")
        try:
            from src.data_fetcher import fetch_market_data, get_sample_data
            market_data = fetch_market_data(data_items)
            if not market_data.get("items"):
                market_data = get_sample_data(data_items)
            n = len(market_data.get("items", []))
            print(f"  量化数据: {n} 项")
            for e in market_data.get("errors", []):
                print(f"  [WARN] {e}")
        except Exception as e:
            print(f"  [WARN] 量化数据采集失败: {e}")
            try:
                from src.data_fetcher import get_sample_data
                market_data = get_sample_data(data_items)
            except Exception:
                pass
    else:
        print("[2/5] 量化数据采集已禁用")

    # ============================================================
    # [3/5] AI 分析
    # ============================================================
    print("[3/5] AI 分析...")
    ai_result = ai_analyze(articles, cfg)
    print(f"  分析完成 (raw={ai_result.get('raw')})")
    si = ai_result.get("sentiment_index")
    if si is not None:
        print(f"  情绪指数: {si:+.1f}/10")

    # ============================================================
    # [4/5] 渲染图表
    # ============================================================
    chart_specs = []
    if enable_charts and market_data:
        print("[4/5] 渲染图表...")
        try:
            from src.chart_renderer import render_price_trend, render_change_bars
            history = market_data.get("history", {})
            for secid, label in [("HGF", "COMEX铜"), ("CU0", "沪铜主力"), ("AL0", "沪铝主力")]:
                p = render_price_trend(history, secid, label)
                if p:
                    chart_specs.append((label, p))
                    print(f"  [OK] 趋势图: {label}")
            p2 = render_change_bars(market_data.get("items", []))
            if p2:
                chart_specs.append(("今日涨跌幅", p2))
                print("  [OK] 涨跌幅柱状图")
        except Exception as e:
            print(f"  [WARN] 图表渲染失败: {e}")
    else:
        print("[4/5] 图表渲染已跳过")

    # ============================================================
    # [5/5] 推送飞书卡片
    # ============================================================
    print("[5/5] 推送飞书卡片...")
    card_limit = settings.get("card_char_limit", 4500)

    # -- Card 1: 摘要卡片 --
    st, sc, scol = build_summary_card(ai_result, today_full, settings)
    if dry:
        print(f"\n=== {st} ({scol}) ===\n{sc}\n")
    else:
        send_card(app_id, app_secret, receive_id, st, sc, scol)
    print("  [OK] 摘要卡片")

    # -- Card 2: KPI 看板卡片（量化数据） --
    if market_data and market_data.get("items"):
        kpi_elems = build_kpi_elements(market_data, settings)
        data_elems = build_data_table(market_data)
        if kpi_elems:
            kpi_title = f"市场数据看板 - {today_full}"
            elements = kpi_elems[:]
            if data_elems:
                elements.append({"tag": "hr"})
                elements.append({"tag": "markdown", "content": "**数据明细**"})
                elements.extend(data_elems)
                ts = market_data.get("timestamp", "")
                if ts:
                    elements.append({"tag": "note",
                                     "elements": [{"tag": "plain_text",
                                                   "content": f"数据采集时间: {ts}"}]})
            if dry:
                print(f"\n=== {kpi_title} ===\n[KPI看板 + 数据明细表]\n")
            else:
                send_elements_card(app_id, app_secret, receive_id, kpi_title,
                                   elements, settings.get("kpi_card_color", "blue"))
            print("  [OK] KPI 看板卡片")

    # -- Card 3: 图表卡片 --
    if chart_specs and not dry:
        image_keys = []
        for label, path in chart_specs:
            key = send_upload(app_id, app_secret, path)
            if key:
                image_keys.append((label, key))
                print(f"  [OK] 图片上传: {label}")
            else:
                print(f"  [WARN] 图片上传失败: {label}")
        if image_keys:
            chart_elems = build_chart_elements(image_keys, settings)
            chart_title = f"量化图表 - {today_full}"
            send_elements_card(app_id, app_secret, receive_id, chart_title,
                               chart_elems, settings.get("chart_card_color", "wathet"))
            print("  [OK] 图表卡片")
    elif chart_specs and dry:
        for label, path in chart_specs:
            print(f"\n=== 图表: {label} ===\n{path}\n")

    # -- Card 4+: 报告正文 --
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

    # -- Cards: 信源列表 --
    for title, content, color in build_source_cards(articles, today_short, settings):
        if dry:
            print(f"\n=== {title} ({color}) ===\n{content}\n")
        else:
            send_card(app_id, app_secret, receive_id, title, content, color)
        print(f"  [OK] {title}")

    if not dry:
        _mark_pushed(today_full)

    print("Done!")


def send_upload(app_id, app_secret, path):
    """上传图片并返回 image_key（封装 upload_image）。"""
    from src.feishu_bot import upload_image
    return upload_image(app_id, app_secret, path)


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
