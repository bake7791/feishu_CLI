"""新闻采集模块 —— Google News + 自定义 RSS，纯配置驱动"""

import urllib.parse
import xml.etree.ElementTree as ET
import time as time_module

from .utils import http_get, parse_rss_date

# 默认屏蔽关键词（settings 可覆盖）
_DEFAULT_SKIP = ["stock", "share price", "sponsored", "advertisement"]


def _should_skip(title, keywords):
    """检查标题是否包含屏蔽关键词，不区分大小写。"""
    lower = title.lower()
    return any(kw in lower for kw in keywords)


def search_google_news(query, hl, gl, ceid_map, skip_keywords, max_results=50):
    """Google News RSS 检索。

    Args:
        query: 检索关键词
        hl: 语言代码 (如 en-US)
        gl: 国家代码 (如 US)
        ceid_map: ceid 映射字典
        skip_keywords: 屏蔽关键词列表
        max_results: 最大返回数量

    Returns:
        list[dict]: 文章列表
    """
    ceid = ceid_map.get(gl, f'{gl}:{hl.split("-")[0]}')
    rss_url = (
        f"https://news.google.com/rss/search?"
        f"q={urllib.parse.quote(query)}&hl={hl}&gl={gl}&ceid={ceid}"
    )
    xml_data = http_get(rss_url, {"User-Agent": "Mozilla/5.0"})
    root = ET.fromstring(xml_data)

    results = []
    for item in root.findall(".//item"):
        t = item.find("title")
        l = item.find("link")
        s = item.find("source")
        p = item.find("pubDate")

        title = t.text.strip() if t is not None and t.text else ""
        link = l.text if l is not None else ""
        source = s.text.strip() if s is not None and s.text else "Unknown"
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
    """自定义 RSS 源抓取。

    Args:
        rss_url: RSS 地址
        region: 地区代码
        source_name: 来源名称
        skip_keywords: 屏蔽关键词列表
        max_results: 最大返回数量

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

        title = t.text.strip() if t is not None and t.text else ""
        link = l.text if l is not None else ""
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
    """采集所有信源，去重并排序。

    去重策略：URL 优先为主键，URL 为空时使用标题前 100 字符。

    Args:
        sources_cfg: sources.json 的 dict（含 queries/feeds/max_articles）
        ceid_map: settings 中的 ceid_map
        skip_keywords: 屏蔽关键词列表，默认使用内置列表
        _print: 日志输出函数（便于测试注入）

    Returns:
        list[dict]: 去重排序后的文章列表
    """
    if skip_keywords is None:
        skip_keywords = [w.lower() for w in _DEFAULT_SKIP]
    else:
        skip_keywords = [w.lower() for w in skip_keywords]

    seen_urls = set()
    seen_titles = set()
    all_results = []

    # Google News 多语言检索
    for q in sources_cfg["queries"]:
        try:
            time_module.sleep(0.5)
            results = search_google_news(
                q["query"], q["hl"], q["gl"],
                ceid_map, skip_keywords)
            _print(f"  [INFO] [{q['gl']}] -> {len(results)} results")
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
            _print(f"  [WARN] [{q['gl']}]: {e}")

    # 自定义 RSS 源
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

    # 按时间降序排列
    all_results.sort(
        key=lambda r: parse_rss_date(r.get("date", "")),
        reverse=True,
    )
    return all_results[:sources_cfg["max_articles"]]
