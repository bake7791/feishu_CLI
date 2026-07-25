"""
================================================================================
新闻采集模块 (crawler.py)
================================================================================
职责：从 Google News 和自定义 RSS 源采集新闻，去重排序后返回。

数据流：
  Google News RSS  ─┐
  自定义 RSS 源   ─┤──→ 过滤屏蔽词 ──→ URL/标题去重 ──→ 按时间排序 ──→ 截断输出
  (sources.json)   ─┘

设计要点：
  1. 纯配置驱动：所有信源在 sources.json 中定义，新增/修改信源无需改代码
  2. 去重策略：URL 优先为主键（同一文章不会重复），URL 为空时用标题前 100 字符
  3. 屏蔽词可配置：从 settings.json 的 skip_keywords 读取，不硬编码

修改指南：
  - 新增信源：编辑 config/sources.json，无需改此文件
  - 调整去重逻辑：修改 search_all() 中的 seen_urls/seen_titles 部分
  - 新增采集渠道（如 Twitter/API）：新建函数，在 search_all() 中调用
================================================================================
"""

import urllib.parse
import xml.etree.ElementTree as ET
import time as time_module

from .utils import http_get, parse_rss_date

# ── 默认屏蔽关键词（settings.json 中 skip_keywords 字段可覆盖） ──
_DEFAULT_SKIP = [
    "stock",             # 股票行情（与大宗商品无关的股市新闻）
    "share price",       # 股价报道
    "sponsored",         # 广告/软文标识
    "advertisement",     # 广告
]


def _should_skip(title, keywords):
    """检查标题是否包含屏蔽关键词，不区分大小写。
    
    Args:
        title:    新闻标题
        keywords: 屏蔽关键词列表（已转为小写）
    
    Returns:
        bool: True 表示应跳过此条新闻
    """
    lower = title.lower()
    return any(kw in lower for kw in keywords)


def search_google_news(query, hl, gl, ceid_map, skip_keywords, max_results=50):
    """从 Google News RSS 检索新闻。
    
    Google News 支持多语言、多地区检索，通过 hl（语言）和 gl（国家）参数控制。
    ceid 是 Google 的地区标识码，不同国家编码不同，在 settings.json 中配置映射。
    
    Args:
        query:         检索关键词（如 "copper price"）
        hl:            语言代码（如 "en-US", "zh-CN"）
        gl:            国家代码（如 "US", "CN"）
        ceid_map:      ceid 映射字典，来自 settings.json
        skip_keywords: 屏蔽关键词列表
        max_results:   单次检索最大返回数量
    
    Returns:
        list[dict]: 文章列表，每条包含 title/url/source/date/region
    """
    # 构造 RSS URL：拼接参数并编码关键词
    ceid = ceid_map.get(gl, f'{gl}:{hl.split("-")[0]}')
    rss_url = (
        f"https://news.google.com/rss/search?"
        f"q={urllib.parse.quote(query)}&hl={hl}&gl={gl}&ceid={ceid}"
    )

    # 获取并解析 XML
    xml_data = http_get(rss_url, {"User-Agent": "Mozilla/5.0"})
    root = ET.fromstring(xml_data)

    results = []
    for item in root.findall(".//item"):
        t = item.find("title")
        l = item.find("link")
        s = item.find("source")
        p = item.find("pubDate")

        title   = t.text.strip() if t is not None and t.text else ""
        link    = l.text if l is not None else ""
        source  = s.text.strip() if s is not None and s.text else "Unknown"
        pubdate = p.text if p is not None else ""

        if not title or _should_skip(title, skip_keywords):
            continue

        results.append({
            "title":  title,
            "url":    link,
            "source": source,
            "date":   pubdate,
            "region": gl,
        })
        if len(results) >= max_results:
            break
    return results


def search_direct_rss(rss_url, region, source_name, skip_keywords, max_results=20):
    """从自定义 RSS 源抓取新闻。
    
    与 Google News 不同，自定义 RSS 不需要 ceid/lang/gl 参数，
    直接访问 RSS 地址即可。适用于行业媒体、专业数据网站等自有 RSS 源。
    
    Args:
        rss_url:       RSS 地址（如 "https://example.com/feed"）
        region:        地区代码（用于分组展示）
        source_name:   来源名称（显示在卡片中）
        skip_keywords: 屏蔽关键词列表
        max_results:   单次最大返回数量
    
    Returns:
        list[dict]: 文章列表
    """
    xml_data = http_get(rss_url, {"User-Agent": "Mozilla/5.0"})
    root = ET.fromstring(xml_data)

    results = []
    for item in root.findall(".//item"):
        t = item.find("title")
        l = item.find("link")
        p = item.find("pubDate")

        title   = t.text.strip() if t is not None and t.text else ""
        link    = l.text if l is not None else ""
        pubdate = p.text if p is not None else ""

        if not title or _should_skip(title, skip_keywords):
            continue

        results.append({
            "title":  title,
            "url":    link,
            "source": source_name,
            "date":   pubdate,
            "region": region,
        })
        if len(results) >= max_results:
            break
    return results


def search_all(sources_cfg, ceid_map, skip_keywords=None, _print=print):
    """采集所有信源，去重排序后返回最终文章列表。
    
    这是采集流程的总入口，依次执行：
      1. 遍历 Google News 检索词 → 采集
      2. 遍历自定义 RSS 源 → 采集
      3. URL 去重（同一篇文章在多个信源出现只保留一条）
      4. 按发布时间降序排列
      5. 截断到 max_articles 限制
    
    Args:
        sources_cfg:   sources.json 的内容（含 queries/feeds/max_articles）
        ceid_map:      settings.json 中的 ceid_map
        skip_keywords: 屏蔽关键词列表，默认使用 _DEFAULT_SKIP
        _print:        日志输出函数（便于测试时注入 mock）
    
    Returns:
        list[dict]: 去重排序后的文章列表
    """
    # 处理屏蔽关键词：配置未提供时使用默认列表
    if skip_keywords is None:
        skip_keywords = [w.lower() for w in _DEFAULT_SKIP]
    else:
        skip_keywords = [w.lower() for w in skip_keywords]

    # 去重数据结构：URL 集合（主键）+ 标题集合（备用）
    seen_urls   = set()
    seen_titles = set()
    all_results = []

    # ── 第 1 步：Google News 多语言检索 ──
    for q in sources_cfg["queries"]:
        try:
            time_module.sleep(0.5)  # 限速，避免触发 Google 反爬
            results = search_google_news(
                q["query"], q["hl"], q["gl"],
                ceid_map, skip_keywords)
            _print(f"  [INFO] [{q['gl']}] -> {len(results)} results")

            for r in results:
                url = r.get("url", "")
                if url:
                    if url in seen_urls:       # URL 去重（精确匹配）
                        continue
                    seen_urls.add(url)
                else:
                    # URL 为空时（极少见），用标题前 100 字符作为备用去重键
                    title_key = r["title"][:100]
                    if title_key in seen_titles:
                        continue
                    seen_titles.add(title_key)
                all_results.append(r)

        except Exception as e:
            _print(f"  [WARN] [{q['gl']}]: {e}")  # 单个信源失败不中断其他采集

    # ── 第 2 步：自定义 RSS 源 ──
    for feed in sources_cfg.get("feeds", []):
        try:
            results = search_direct_rss(
                feed["url"], feed["region"],
                feed.get("name", "RSS"), skip_keywords)
            _print(f"  [INFO] [RSS:{feed.get('name')}] -> {len(results)} results")

            for r in results:
                url = r.get("url", "")
                if url:
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                else:
                    title_key = r["title"][:100]
                    if title_key in seen_titles:
                        continue
                    seen_titles.add(title_key)
                all_results.append(r)

        except Exception as e:
            _print(f"  [WARN] [RSS:{feed.get('name')}]: {e}")

    # ── 第 3 步：排序 + 截断 ──
    # 按 pubDate 降序排列（最新的排最前），解析失败的自动排到末尾
    all_results.sort(
        key=lambda r: parse_rss_date(r.get("date", "")),
        reverse=True,
    )
    return all_results[:sources_cfg["max_articles"]]
