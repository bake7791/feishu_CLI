"""
================================================================================
量化数据采集模块 (data_fetcher.py) —— 配置驱动版
================================================================================
职责：根据 report_config.json 中的 data_items 配置动态采集市场数据。

支持的 source 类型：
  yahoo      Yahoo Finance（全球可访问，CI 友好）
  eastmoney  东方财富（国内期货，带新浪 fallback）
  sina       新浪财经（国内期货备用源）

设计要点：
  1. 完全配置驱动——增删品种只需改 JSON，不改代码
  2. 数据采集框架不变，只是 fetch 逻辑按 config 分发
  3. 价格数值绝不经过 AI，直接从数据源渲染到卡片
================================================================================
"""

import json
import re
from datetime import datetime, timedelta

from .utils import http_get


# ================================================================
# Yahoo Finance 数据源
# ================================================================

_YF_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}"
_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def _fetch_yahoo(symbol):
    """从 Yahoo Finance 获取行情 + 近7日历史。"""
    url = f"{_YF_URL.format(symbol)}?interval=1d&range=8d"
    text = http_get(url, headers=_YF_HEADERS, timeout=15)
    data = json.loads(text)
    result = data["chart"]["result"][0]
    meta = result["meta"]
    price = meta.get("regularMarketPrice")
    prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")

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
# 东方财富 数据源
# ================================================================

_EM_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
_EM_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_EM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
}


def _fetch_eastmoney(market, symbol):
    """东方财富期货实时行情。market 如 "113"（上期所），symbol 如 "CU0"。"""
    secid = f"{market}.{symbol}"
    url = f"{_EM_QUOTE_URL}?secid={secid}&fields=f43,f57,f58,f60,f169,f170"
    text = http_get(url, headers=_EM_HEADERS, timeout=15)
    data = json.loads(text)
    d = data.get("data")
    if not d or not d.get("f43"):
        return None
    price = d["f43"] / 100.0
    prev_close = d.get("f60", 0) / 100.0 if d.get("f60") else None
    return {"price": price, "prev_close": prev_close, "history": None}


def _fetch_eastmoney_kline(market, symbol, days=7):
    """东方财富近N日K线。"""
    secid = f"{market}.{symbol}"
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
# 新浪财经 数据源（国内期货 fallback）
# ================================================================

_SINA_URL = "https://hq.sinajs.cn/list={}"
_SINA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn/",
}


def _fetch_sina(symbols):
    """批量从新浪获取期货行情。symbols 如 ["CU0", "AL0"]。"""
    url = _SINA_URL.format(",".join(symbols))
    text = http_get(url, headers=_SINA_HEADERS, timeout=10)
    results = {}
    for line in text.strip().splitlines():
        if not line.strip():
            continue
        m = re.match(r'var hq_str_(\w+)="(.+)"', line.strip())
        if not m:
            continue
        sym = m.group(1)
        fields = m.group(2).split(",")
        if len(fields) < 4:
            continue
        try:
            price = float(fields[3]) if fields[3] else None
            prev_close = float(fields[2]) if fields[2] else None
        except (ValueError, TypeError):
            continue
        if price and price > 0:
            results[sym] = {"price": price, "prev_close": prev_close or price, "history": None}
    return results


# ================================================================
# 标准化数据项构建
# ================================================================

def _make_item(item_config, price, prev_close):
    """将配置 + 采集到的数据组装为标准 dict。"""
    name = item_config["name"]
    unit = item_config.get("unit", "")
    exchange = item_config.get("exchange", "")
    region = item_config.get("region", "GLOBAL")
    category = item_config.get("category", "")

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
        "source": exchange,
        "region": region,
        "category": category,
        "time": datetime.now().strftime("%H:%M"),
    }


# ================================================================
# 配置驱动的主采集函数
# ================================================================

def _fetch_one(item):
    """根据单个 data_items 配置项采集数据。

    返回: (item_dict_or_None, history_dict_or_None, symbol_for_chart_or_None)
    """
    source = item.get("source", "yahoo")
    symbol = item.get("symbol", "")
    market = item.get("market", "")
    fallback = item.get("fallback", "")
    result = None
    history = None
    chart_id = None

    if source == "yahoo":
        result = _fetch_yahoo(symbol)
        if result:
            chart_id = symbol

    elif source == "eastmoney":
        result = _fetch_eastmoney(market, symbol)
        if result:
            chart_id = symbol
        # 东方财富失败 → 尝试新浪 fallback
        if not result and fallback == "sina":
            sina_results = _fetch_sina([symbol])
            if symbol in sina_results:
                result = sina_results[symbol]

    elif source == "sina":
        sina_results = _fetch_sina([symbol])
        if symbol in sina_results:
            result = sina_results[symbol]
            chart_id = symbol

    if not result or not result.get("price"):
        return None, None, None

    item_dict = _make_item(item, result["price"], result["prev_close"])
    history = result.get("history")

    # 东方财富的 K 线需要单独拉取
    if source == "eastmoney" and history is None:
        try:
            history = _fetch_eastmoney_kline(market, symbol)
        except Exception:
            pass

    return item_dict, history, chart_id


def fetch_market_data(data_items):
    """根据配置列表采集全部市场数据。

    Args:
        data_items: report_config["data_items"] 列表

    Returns:
        dict: {timestamp, items, history, errors}
    """
    items = []
    history = {}
    errors = []

    for item in data_items:
        if not item.get("enabled", True):
            continue
        try:
            item_dict, hist, chart_id = _fetch_one(item)
            if item_dict:
                items.append(item_dict)
            if hist and chart_id:
                history[chart_id] = hist
        except Exception as e:
            errors.append(f"{item.get('name', '?')} 采集失败: {e}")

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "items": items,
        "history": history,
        "errors": errors,
    }


# ================================================================
# 示例数据（备用）
# ================================================================

def get_sample_data(data_items):
    """只用启用的 data_items 生成示例数据。"""
    sample_prices = {
        "铜": (418.5, 413.2), "沪铜": (78450, 77830),
        "铝": (19800, 19700), "沪铝": (19800, 19700),
        "COMEX": (418.5, 413.2), "美元": (104.2, 103.9),
        "指数": (104.2, 103.9),
    }

    def _guess_price(name):
        for k, v in sample_prices.items():
            if k in name:
                return v
        return (100.0, 99.0)

    items = []
    for item in data_items:
        if not item.get("enabled", True):
            continue
        price, prev = _guess_price(item["name"])
        it = _make_item(item, price, prev)
        if it:
            items.append(it)

    dates = [(datetime.now() - timedelta(days=6 - i)).strftime("%m-%d") for i in range(7)]
    sample_history = {}
    for item in data_items:
        if item.get("source") == "yahoo":
            sample_history[item.get("symbol", "")] = {
                "dates": dates,
                "prices": [413.0, 414.5, 415.8, 415.0, 416.2, 417.5, 418.5],
            }

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "items": items,
        "history": sample_history,
        "errors": ["使用示例数据（数据源不可用）"],
    }
