"""
================================================================================
图表渲染模块 (chart_renderer.py)
================================================================================
职责：使用 matplotlib 将量化数据渲染为 PNG 图表，供飞书卡片嵌入展示。
     这是企业自建应用相比群机器人 Webhook 的核心优势——能发图片。

图表类型：
  1. render_price_trend()  近7日价格趋势折线图
  2. render_change_bars()  当日涨跌幅横向柱状图

中文字体处理：
  - 自动检测系统中文字体（Noto CJK / 微软雅黑 / 文泉驿等）
  - 找不到时自动降级为英文标签，避免乱码
  - GitHub Actions 中通过 apt install fonts-noto-cjk 安装
================================================================================
"""

import os
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

# 全局状态
_state = {"chart_dir": None, "cn_font_ok": False, "setup_done": False}

# 中文字体候选路径（Linux Noto CJK / Windows 微软雅黑 / 文泉驿）
_FONT_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
]

# 品种名英文映射（中文字体不可用时降级）
_NAME_EN = {
    "沪铜主力": "SHFE Cu",
    "LME铜3M": "LME Cu",
    "沪铝主力": "SHFE Al",
    "美元指数": "USD Index",
}

# 颜色方案（中国习惯：涨红跌绿）
_C_UP = "#e74c3c"
_C_DOWN = "#27ae60"
_C_LINE = "#2980b9"


def _setup():
    """初始化图表环境：字体检测 + 临时目录。"""
    if _state["setup_done"]:
        return
    _state["setup_done"] = True
    _state["chart_dir"] = tempfile.mkdtemp(prefix="charts_")

    for path in _FONT_PATHS:
        if os.path.exists(path):
            try:
                font_manager.fontManager.addfont(path)
                prop = font_manager.FontProperties(fname=path)
                plt.rcParams["font.sans-serif"] = [prop.get_name()]
                plt.rcParams["axes.unicode_minus"] = False
                _state["cn_font_ok"] = True
                return
            except Exception:
                continue


def _name(label):
    """品种名显示：有中文字体用原名，否则用英文。"""
    if _state["cn_font_ok"]:
        return label
    return _NAME_EN.get(label, label)


def _path(filename):
    """返回图表文件的完整路径。"""
    _setup()
    return os.path.join(_state["chart_dir"], filename)


def render_price_trend(history, secid, label=""):
    """渲染近7日价格趋势折线图。

    Args:
        history: fetch_market_data() 返回的 history 字典
        secid:   品种代码（如 "CU0"）
        label:   图表标题中的品种名

    Returns:
        str: PNG 文件路径，None 表示无数据
    """
    _setup()
    if secid not in history:
        return None
    data = history[secid]
    dates = data["dates"]
    prices = data["prices"]
    if len(prices) < 2:
        return None

    fig, ax = plt.subplots(figsize=(8, 3.5), dpi=100)

    x = range(len(dates))
    ax.plot(x, prices, color=_C_LINE, linewidth=2, marker="o", markersize=4)
    y_min = min(prices)
    y_max = max(prices)
    pad = (y_max - y_min) * 0.15 if y_max > y_min else y_max * 0.02
    ax.fill_between(x, prices, y_min - pad, alpha=0.12, color=_C_LINE)

    # 标注最新价格
    ax.annotate(
        f"{prices[-1]:,.0f}",
        xy=(len(dates) - 1, prices[-1]),
        xytext=(8, 10), textcoords="offset points",
        fontsize=11, fontweight="bold", color=_C_LINE,
    )

    # 涨跌决定底色
    if prices[-1] >= prices[0]:
        ax.set_facecolor("#fdf6f6")
    else:
        ax.set_facecolor("#f6fdf6")

    title = f"{_name(label)} - 7D" if _state["cn_font_ok"] else f"{_NAME_EN.get(label, label)} - 7D"
    ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
    ax.set_xticks(x)
    ax.set_xticklabels(dates)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    out = _path(f"trend_{secid}.png")
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def render_change_bars(items):
    """渲染当日涨跌幅横向柱状图。

    Args:
        items: fetch_market_data() 返回的 items 列表

    Returns:
        str: PNG 文件路径，None 表示无数据
    """
    _setup()
    valid = [it for it in items if it.get("change_pct") is not None]
    if not valid:
        return None

    labels = [_name(it["name"]) for it in valid]
    values = [it["change_pct"] for it in valid]
    colors = [_C_UP if v >= 0 else _C_DOWN for v in values]

    fig, ax = plt.subplots(figsize=(8, max(2.5, len(valid) * 0.6 + 1)), dpi=100)
    bars = ax.barh(labels, values, color=colors, height=0.5, edgecolor="white")

    for bar, v in zip(bars, values):
        offset = 0.05 if v >= 0 else -0.05
        ax.text(v + offset, bar.get_y() + bar.get_height() / 2,
                f"{v:+.2f}%", va="center",
                ha="left" if v >= 0 else "right",
                fontsize=10, fontweight="bold")

    title = "今日涨跌幅" if _state["cn_font_ok"] else "Today's Change (%)"
    ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
    ax.axvline(0, color="#bdc3c7", linewidth=0.8)
    ax.grid(True, axis="x", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    margin = max(abs(max(values)), abs(min(values))) * 0.35
    ax.set_xlim(min(values) - margin, max(values) + margin)

    out = _path("change_bars.png")
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out
