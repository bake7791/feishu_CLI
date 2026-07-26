"""
================================================================================
量化数据采集模块 (data_fetcher.py)
================================================================================
职责：采集全球铜及预焙阳极相关的量化市场数据。

数据源（B 方案：国际为主 + 国内主力保留）：
  国际源（Yahoo Finance，全球可访问，CI 友好）：
    - COMEX 铜 (HG=F)：国际铜价基准
    - 美元指数 (DX-Y.NYB)：宏观指标
  国内源（东方财富，保留主力合约）：
    - 沪铜主力 (CU0)：国内铜价基准
    - 沪铝主力 (AL0)：阳极下游

设计要点：
  1. 国际源优先采集，国内源失败时自动降级不影响整体
  2. Yahoo Finance chart API 同时返回实时价 + 近7日历史，一次调用搞定
  3. 价格数值绝不经过 AI，直接从数据源渲染到卡片
================================================================================
"""

import json
from datetime import datetime, timedelta

from .utils import http_get


# ================================================================
# 国际源：Yahoo Finance（全球可访问，CI 友好）
# ================================================================

_YF_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}"
_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def _fetch_yf_quote(symbol):
    """从 Yahoo Finance 获取行情 + 近7日历史。

    Yahoo Finance chart API 一次调用同时返回：
      - regularMarketPrice: 实时价
      - chartPreviousClose:  前收盘价
      - 近 N 日收盘价序列（趋势图用）
    """
    url = f"{_YF_URL.format(symbol)}?interval=1d&range=8d"
    text = http_get(url, headers=_YF_HEADERS, timeout=15)
    data = json.loads(text)
    result = data["chart"]["result"][0]
    meta = result["meta"]
    price = meta.get("regularMarketPrice")
    prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")

    # 近7日收盘价
    timestamps = result.get("timestamp", [])
    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    dates, prices = [], []
    for ts, c in zip(timestamps, closes):
        if c is not None:
            dates.append(datetime.utcfromtimestamp(ts).strftime("%m-%d"))
            prices.append(round(c, 2))
    dates = dates[-7:]
    prices = prices[-7:]

    return {
        "price": price,
        "prev_close": prev_close,
        "history": {"dates": dates, "prices": prices} if prices else None,
    }


# ================================================================
# 国内源：东方财富（沪铜/沪铝主力，带 UA 伪装 + Referer）
# ================================================================

_EM_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
_EM_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_EM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
}
_EM_SHFE = "113"


def _fetch_em_quote(secid):
    """东方财富期货实时行情。"""
    url = f"{_EM_QUOTE_URL}?secid={secid}&fields=f43,f57,f58,f60,f169,f170"
    text = http_get(url, headers=_EM_HEADERS, timeout=15)
    data = json.loads(text)
    d = data.get("data")
    if not d or not d.get("f43"):
        return None
    price = d["f43"] / 100.0
    prev_close = d.get("f60", 0) / 100.0 if d.get("f60") else None
    return {"price": price, "prev_close": prev_close}


def _fetch_em_kline(secid, days=7):
    """东方财富近N日K线。"""
    end = datetime.now().strftime("%Y%m%d")
    beg = (datetime.now() - timedelta(days=days + 5)).strftime("%Y%m%d")
    url = (f"{_EM_KLINE_URL}?secid={secid}&klt=101&fqt=0"
           f"&beg={beg}&end={end}&fields1=f1,f2,f3&fields2=f51,f53")
    text = http_get(url, headers=_EM_HEADERS, timeout=15)
    data = json.loads(text)
    klines = data.get("data", {}).get("klines", [])
    if not klines:
        return None
    dates, prices = [], []
    for line in klines:
        parts = line.split(",")
        if len(parts) >= 2:
            dates.append(parts[0][5:])
            prices.append(float(parts[1]))
    return {"dates": dates[-days:], "prices": prices[-days:]} if prices else None


# ================================================================
# 标准化数据项构建
# ================================================================

def _make_item(name, price, prev_close, unit, source, region, category):
    if price is None or price <= 0:
        return None
    prev_close = prev_close or price
    change = round(price - prev_close, 2)
    change_pct = round(change / prev_close * 100, 2) if prev_close else 0.0
    return {
        "name": name, "price": round(price, 2), "prev_close": round(prev_close, 2),
        "change": change, "change_pct": change_pct, "unit": unit,
        "source": source, "region": region, "category": category,
        "time": datetime.now().strftime("%H:%M"),
    }


# ================================================================
# 分类采集（国际为主 + 国内主力）
# ================================================================

def _fetch_copper():
    """铜价：COMEX铜（国际）+ 沪铜（国内主力）。"""
    items = []
    history = {}
    # 国际：COMEX 铜
    try:
        d = _fetch_yf_quote("HG=F")
        if d:
            items.append(_make_item("COMEX铜", d["price"], d["prev_close"],
                                    "美分/磅", "COMEX", "GLOBAL", "copper"))
            if d.get("history"):
                history["HGF"] = d["history"]
    except Exception:
        pass
    # 国内主力：沪铜
    try:
        d = _fetch_em_quote(f"{_EM_SHFE}.CU0")
        if d:
            items.append(_make_item("沪铜主力", d["price"], d["prev_close"],
                                    "元/吨", "SHFE", "CN", "copper"))
        k = _fetch_em_kline(f"{_EM_SHFE}.CU0")
        if k:
            history["CU0"] = k
    except Exception:
        pass
    return items, history


def _fetch_aluminum():
    """铝价：沪铝（阳极下游，国内主力）。"""
    items = []
    history = {}
    try:
        d = _fetch_em_quote(f"{_EM_SHFE}.AL0")
        if d:
            items.append(_make_item("沪铝主力", d["price"], d["prev_close"],
                                    "元/吨", "SHFE", "CN", "aluminum"))
        k = _fetch_em_kline(f"{_EM_SHFE}.AL0")
        if k:
            history["AL0"] = k
    except Exception:
        pass
    return items, history


def _fetch_macro():
    """宏观：美元指数（国际源）。"""
    items = []
    history = {}
    try:
        d = _fetch_yf_quote("DX-Y.NYB")
        if d:
            items.append(_make_item("美元指数", d["price"], d["prev_close"],
                                    "", "ICE", "GLOBAL", "macro"))
    except Exception:
        pass
    return items, history


# ================================================================
# 主函数
# ================================================================

def fetch_market_data():
    """采集全部市场数据。

    国际源（COMEX铜/美元指数）优先采集且 CI 可访问，
    国内源（沪铜/沪铝）失败时自动降级不影响国际数据。
    """
    items = []
    history = {}
    errors = []
    for name, fetcher in [
        ("铜价", _fetch_copper),
        ("铝价", _fetch_aluminum),
        ("宏观", _fetch_macro),
    ]:
        try:
            its, hist = fetcher()
            items.extend(its)
            history.update(hist)
        except Exception as e:
            errors.append(f"{name}采集失败: {e}")
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "items": items, "history": history, "errors": errors,
    }


# ================================================================
# 示例数据（DRY_RUN 降级用）
# ================================================================

def get_sample_data():
    """返回示例市场数据，用于 DRY_RUN 预览和数据源不可用时的降级。"""
    base = {
        "COMEX铜": (418.5, 413.2, "美分/磅", "COMEX", "GLOBAL", "copper"),
        "沪铜主力": (78450, 77830, "元/吨", "SHFE", "CN", "copper"),
        "沪铝主力": (19800, 19700, "元/吨", "SHFE", "CN", "aluminum"),
        "美元指数": (104.2, 103.9, "", "ICE", "GLOBAL", "macro"),
    }
    items = [_make_item(n, p, pc, u, s, r, c) for n, (p, pc, u, s, r, c) in base.items()]
    dates = [(datetime.now() - timedelta(days=6 - i)).strftime("%m-%d") for i in range(7)]
    history = {
        "HGF": {"dates": dates, "prices": [413.0, 414.5, 415.8, 415.0, 416.2, 417.5, 418.5]},
        "CU0": {"dates": dates, "prices": [77800, 77950, 78100, 78050, 78200, 78300, 78450]},
        "AL0": {"dates": dates, "prices": [19650, 19680, 19720, 19690, 19750, 19780, 19800]},
    }
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "items": items, "history": history,
        "errors": ["使用示例数据（DRY_RUN 模式或数据源不可用）"],
    }
