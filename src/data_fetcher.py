"""
================================================================================
量化数据采集模块 (data_fetcher.py)
================================================================================
职责：采集全球铜及预焙阳极相关的量化市场数据（期货价格、宏观指标），
     为图表渲染和 KPI 看板提供数据支撑。

数据源（均为免费公开接口）：
  1. 东方财富期货行情（国内期货实时 + K线历史）
  2. 新浪财经外盘行情（LME铜、美元指数等）

设计要点：
  1. 每个数据源独立 try/except，单个失败不影响整体
  2. 返回标准化数据结构，供图表和卡片渲染层使用
  3. 提供 get_sample_data() 示例数据，用于 DRY_RUN 和降级
  4. 价格数值绝不经过 AI，直接从数据源渲染到卡片
================================================================================
"""

import json
import re
from datetime import datetime, timedelta

from .utils import http_get


# -- 东方财富期货行情接口 --
_EM_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
_EM_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_EM_HEADERS = {"User-Agent": "Mozilla/5.0"}

# -- 新浪财经外盘行情接口 --
_SINA_HQ_URL = "https://hq.sinajs.cn/list={}"
_SINA_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0",
}

# secid 前缀：113=上期所(SHFE)
_EM_SHFE = "113"


# ================================================================
# 标准化数据项构建
# ================================================================

def _make_item(name, price, prev_close, unit, source, region, category):
    """构建标准化市场数据项。"""
    if price is None or price <= 0:
        return None
    prev_close = prev_close or price
    change = round(price - prev_close, 2)
    change_pct = round(change / prev_close * 100, 2) if prev_close else 0.0
    return {
        "name": name,
        "price": round(price, 2),
        "prev_close": round(prev_close, 2),
        "change": change,
        "change_pct": change_pct,
        "unit": unit,
        "source": source,
        "region": region,
        "category": category,
        "time": datetime.now().strftime("%H:%M"),
    }


# ================================================================
# 东方财富：国内期货实时行情
# ================================================================

def _fetch_em_quote(secid):
    """从东方财富获取期货行情快照。

    东方财富期货数据价格字段以"分"为单位（放大100倍），
    此函数自动还原为实际值。
    """
    url = (
        f"{_EM_QUOTE_URL}?secid={secid}"
        "&fields=f43,f57,f58,f60,f169,f170"
    )
    text = http_get(url, headers=_EM_HEADERS, timeout=15)
    data = json.loads(text)
    d = data.get("data")
    if not d or not d.get("f43"):
        return None
    price = d["f43"] / 100.0
    prev_close = d.get("f60", 0) / 100.0 if d.get("f60") else None
    name = d.get("f58", "")
    return {"name": name, "price": price, "prev_close": prev_close}


def _fetch_em_kline(secid, days=7):
    """从东方财富获取近 N 日日K收盘价序列，用于趋势图。"""
    end = datetime.now().strftime("%Y%m%d")
    beg = (datetime.now() - timedelta(days=days + 5)).strftime("%Y%m%d")
    url = (
        f"{_EM_KLINE_URL}?secid={secid}&klt=101&fqt=0"
        f"&beg={beg}&end={end}"
        "&fields1=f1,f2,f3&fields2=f51,f53"
    )
    text = http_get(url, headers=_EM_HEADERS, timeout=15)
    data = json.loads(text)
    klines = data.get("data", {}).get("klines", [])
    if not klines:
        return None
    dates, prices = [], []
    for line in klines:
        parts = line.split(",")
        if len(parts) >= 2:
            dates.append(parts[0][5:])  # MM-DD
            prices.append(float(parts[1]))
    dates = dates[-days:]
    prices = prices[-days:]
    return {"dates": dates, "prices": prices} if prices else None


# ================================================================
# 新浪：外盘期货行情
# ================================================================

def _fetch_sina_quote(symbol):
    """从新浪财经获取外盘期货行情。

    新浪外盘接口格式：var hf_XXX="名称,当前价,买价,卖价,昨结,...";
    """
    url = _SINA_HQ_URL.format(symbol)
    text = http_get(url, headers=_SINA_HEADERS, timeout=15)
    m = re.search(r'="([^"]*)"', text)
    if not m:
        return None
    fields = m.group(1).split(",")
    if len(fields) < 5:
        return None
    name = fields[0]
    price = float(fields[1]) if fields[1] else None
    prev_close = float(fields[4]) if fields[4] else None
    if not price or price <= 0:
        return None
    return {"name": name, "price": price, "prev_close": prev_close}


# ================================================================
# 分类采集
# ================================================================

def _fetch_copper():
    """采集铜价数据：沪铜、LME铜"""
    items = []
    try:
        d = _fetch_em_quote(f"{_EM_SHFE}.CU0")
        if d:
            items.append(_make_item(
                "沪铜主力", d["price"], d["prev_close"],
                "元/吨", "SHFE", "CN", "copper",
            ))
    except Exception:
        pass
    try:
        d = _fetch_sina_quote("hf_CU")
        if d:
            items.append(_make_item(
                "LME铜3M", d["price"], d["prev_close"],
                "美元/吨", "LME", "GLOBAL", "copper",
            ))
    except Exception:
        pass
    return items


def _fetch_aluminum():
    """采集铝价数据：沪铝（阳极下游）"""
    items = []
    try:
        d = _fetch_em_quote(f"{_EM_SHFE}.AL0")
        if d:
            items.append(_make_item(
                "沪铝主力", d["price"], d["prev_close"],
                "元/吨", "SHFE", "CN", "aluminum",
            ))
    except Exception:
        pass
    return items


def _fetch_macro():
    """采集宏观指标：美元指数"""
    items = []
    try:
        d = _fetch_sina_quote("hf_DINIW")
        if d:
            items.append(_make_item(
                "美元指数", d["price"], d["prev_close"],
                "", "ICE", "GLOBAL", "macro",
            ))
    except Exception:
        pass
    return items


# ================================================================
# 主函数
# ================================================================

def fetch_market_data():
    """采集全部市场数据，返回标准化结构。

    每个数据源独立采集，失败不影响其他。采集到的数据直接渲染到
    卡片和图表，不经过 AI 处理，确保数字可信。

    Returns:
        dict: {
            "timestamp": 采集时间,
            "items":     [标准化数据项列表],
            "history":   {secid: {dates, prices}},
            "errors":    [失败信息列表],
        }
    """
    items = []
    errors = []

    for name, fetcher in [
        ("铜价", _fetch_copper),
        ("铝价", _fetch_aluminum),
        ("宏观", _fetch_macro),
    ]:
        try:
            result = fetcher()
            items.extend(result)
        except Exception as e:
            errors.append(f"{name}采集失败: {e}")

    history = {}
    for label, secid in [("CU0", f"{_EM_SHFE}.CU0"), ("AL0", f"{_EM_SHFE}.AL0")]:
        try:
            k = _fetch_em_kline(secid)
            if k:
                history[label] = k
        except Exception as e:
            errors.append(f"{label}K线采集失败: {e}")

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "items": items,
        "history": history,
        "errors": errors,
    }


# ================================================================
# 示例数据（DRY_RUN 降级用）
# ================================================================

def get_sample_data():
    """返回示例市场数据，用于 DRY_RUN 预览和数据源不可用时的降级。"""
    base_prices = {
        "沪铜主力": (78450, 77830, "元/吨", "SHFE", "CN", "copper"),
        "LME铜3M": (9180, 9070, "美元/吨", "LME", "GLOBAL", "copper"),
        "沪铝主力": (19800, 19700, "元/吨", "SHFE", "CN", "aluminum"),
        "美元指数": (104.2, 103.9, "", "ICE", "GLOBAL", "macro"),
    }
    items = []
    for name, (p, pc, unit, src, reg, cat) in base_prices.items():
        items.append(_make_item(name, p, pc, unit, src, reg, cat))

    dates = [(datetime.now() - timedelta(days=6 - i)).strftime("%m-%d") for i in range(7)]
    history = {
        "CU0": {"dates": dates, "prices": [77800, 77950, 78100, 78050, 78200, 78300, 78450]},
        "AL0": {"dates": dates, "prices": [19650, 19680, 19720, 19690, 19750, 19780, 19800]},
    }
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "items": items,
        "history": history,
        "errors": ["使用示例数据（DRY_RUN 模式或数据源不可用）"],
    }
