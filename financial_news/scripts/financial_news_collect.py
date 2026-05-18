#!/usr/bin/env python3
"""
每日财经新闻数据采集脚本 (v2 - 反爬优化)
- 抓取 22 个财经网站 (昨日08:00 ~ 今日08:00)
- 伪装正常浏览器用户 (TLS指纹/请求头/时序)
- TF-IDF 粗筛去重 (阈值 0.85)
- 输出 JSON 到 stdout 供 agent 做语义精筛

依赖: httpx, beautifulsoup4, lxml, jieba
"""
import json
import os
import re
import sys
import time
import random
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# ---- 日志写 stderr，stdout 只放 JSON ----
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("fnd")

# ---- 依赖 ----
try:
    import httpx
    import jieba
    from bs4 import BeautifulSoup
    jieba.setLogLevel(jieba.logging.WARNING)
except ImportError:
    VENV = os.path.expanduser("~/financial-news-daily/.venv/lib/python3.11/site-packages")
    if os.path.isdir(VENV):
        sys.path.insert(0, VENV)
        import httpx, jieba
        from bs4 import BeautifulSoup
        jieba.setLogLevel(jieba.logging.WARNING)
    else:
        log.error("缺少依赖: pip install httpx beautifulsoup4 lxml jieba")
        sys.exit(1)

# ============================================================
# 配置
# ============================================================
MAX_PER_SITE = 10
TIMEOUT = 15
MIN_DELAY = 1.2
MAX_DELAY = 4.0
SIM_THRESHOLD = 0.85
MAX_RETRIES = 2

# ---- 浏览器指纹池 (Chrome/Firefox/Safari，覆盖主流版本) ----
BROWSER_PROFILES = [
    # Chrome 125 on Windows
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        "sec_ch_ua_platform": '"Windows"',
        "sec_ch_ua_mobile": "?0",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept_encoding": "gzip, deflate, br, zstd",
        "accept_language": "zh-CN,zh;q=0.9,en;q=0.8",
    },
    # Chrome 125 on macOS
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        "sec_ch_ua_platform": '"macOS"',
        "sec_ch_ua_mobile": "?0",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "accept_encoding": "gzip, deflate, br, zstd",
        "accept_language": "zh-CN,zh;q=0.9,en;q=0.8",
    },
    # Chrome 125 on Linux
    {
        "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        "sec_ch_ua_platform": '"Linux"',
        "sec_ch_ua_mobile": "?0",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "accept_encoding": "gzip, deflate, br, zstd",
        "accept_language": "zh-CN,zh;q=0.9,en;q=0.8",
    },
    # Firefox 126 on Windows
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
        "sec_ch_ua": None,
        "sec_ch_ua_platform": None,
        "sec_ch_ua_mobile": None,
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept_encoding": "gzip, deflate, br, zstd",
        "accept_language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
    },
    # Firefox 126 on macOS
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:126.0) Gecko/20100101 Firefox/126.0",
        "sec_ch_ua": None,
        "sec_ch_ua_platform": None,
        "sec_ch_ua_mobile": None,
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept_encoding": "gzip, deflate, br, zstd",
        "accept_language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
    },
    # Safari 17 on macOS
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "sec_ch_ua": None,
        "sec_ch_ua_platform": None,
        "sec_ch_ua_mobile": None,
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept_encoding": "gzip, deflate, br",
        "accept_language": "zh-CN,zh;q=0.9,en;q=0.8",
    },
    # Chrome 125 on Android (移动端)
    {
        "ua": "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
        "sec_ch_ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        "sec_ch_ua_platform": '"Android"',
        "sec_ch_ua_mobile": "?1",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept_encoding": "gzip, deflate, br, zstd",
        "accept_language": "zh-CN,zh;q=0.9",
    },
]

OFFICIAL = {"发改委", "人民银行", "金管总局", "财政部", "美联储"}

SITES = [
    {"name": "中国经济网", "url": "http://www.ce.cn/", "type": "ce"},
    {"name": "华尔街见闻", "url": "https://wallstreetcn.com/", "type": "wallstreetcn"},
    {"name": "第一财经", "url": "https://www.yicai.com/", "type": "yicai"},
    {"name": "财新", "url": "https://www.caixin.com/", "type": "caixin"},
    {"name": "新浪财经", "url": "https://finance.sina.com.cn/", "type": "sina"},
    {"name": "FT中文网", "url": "https://m.ftchinese.com/", "type": "ftchinese"},
    {"name": "凤凰网财经", "url": "https://finance.ifeng.com/", "type": "ifeng"},
    {"name": "新华财经", "url": "https://www.cnfin.com/", "type": "cnfin"},
    {"name": "发改委", "url": "https://www.ndrc.gov.cn/", "type": "ndrc"},
    {"name": "财政部", "url": "https://www.mof.gov.cn/zhengwuxinxi/", "type": "mof"},
    {"name": "金管总局", "url": "https://www.nfra.gov.cn/cn/view/pages/xinwenzixun/xinwenzixun.html", "type": "nfra"},
    {"name": "人民银行", "url": "https://www.pbc.gov.cn/", "type": "pbc"},
    {"name": "美联储", "url": "https://www.federalreserve.gov/default.htm", "type": "fed"},
    {"name": "财联社", "url": "https://www.cls.cn/", "type": "cls"},
    {"name": "上证报", "url": "https://www.cnstock.com/", "type": "cnstock"},
    {"name": "证券时报", "url": "https://www.stcn.com/", "type": "stcn"},
    {"name": "财新-能源", "url": "https://www.caixin.com/energy/", "type": "caixin_energy"},
    {"name": "百川盈孚", "url": "https://www.baiinfo.com/", "type": "baiinfo"},
    {"name": "36氪", "url": "https://www.36kr.com/", "type": "kr36"},
    {"name": "虎嗅网", "url": "https://www.huxiu.com/", "type": "huxiu"},
    {"name": "TechCrunch", "url": "https://techcrunch.com/", "type": "techcrunch"},
    {"name": "Trading Economics", "url": "https://tradingeconomics.com/", "type": "tradingeconomics"},
]

# ============================================================
# HTTP 客户端 (模拟真实浏览器)
# ============================================================
_client = None
_current_profile = None

def _pick_profile():
    """每次会话随机选一个浏览器指纹"""
    global _current_profile
    if _current_profile is None:
        _current_profile = random.choice(BROWSER_PROFILES)
    return _current_profile

def http():
    global _client
    if _client is None:
        _client = httpx.Client(
            timeout=TIMEOUT,
            follow_redirects=True,
            verify=False,
            # 连接池：保持长连接，减少 TLS 握手次数
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
                keepalive_expiry=30,
            ),
        )
    return _client

def _build_headers(url: str) -> dict:
    """为每次请求构建完整的浏览器请求头"""
    p = _pick_profile()
    headers = {
        "User-Agent": p["ua"],
        "Accept": p["accept"],
        "Accept-Encoding": p["accept_encoding"],
        "Accept-Language": p["accept_language"],
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }
    # Chrome 系列有 Sec-CH-UA 头
    if p.get("sec_ch_ua"):
        headers["Sec-CH-UA"] = p["sec_ch_ua"]
        headers["Sec-CH-UA-Platform"] = p["sec_ch_ua_platform"]
        headers["Sec-CH-UA-Mobile"] = p["sec_ch_ua_mobile"]
        headers["Sec-Fetch-Dest"] = "document"
        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-Site"] = "none"
        headers["Sec-Fetch-User"] = "?1"
    # Referer：模拟从搜索引擎或前一页跳转
    if random.random() < 0.3:
        headers["Referer"] = "https://www.google.com/"
    elif random.random() < 0.5:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
    return headers

def human_delay():
    """模拟人类浏览间隔：随机 + 正态分布，避免固定节奏"""
    base = random.uniform(MIN_DELAY, MAX_DELAY)
    # 正态分布抖动 (±30%)
    jitter = random.gauss(0, base * 0.15)
    delay = max(0.5, base + jitter)
    time.sleep(delay)

def fetch(url: str, retries: int = MAX_RETRIES) -> Optional[str]:
    """带重试和随机延迟的请求"""
    for attempt in range(retries + 1):
        try:
            headers = _build_headers(url)
            r = http().get(url, headers=headers)
            r.raise_for_status()
            return r.text
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 403:
                log.warning(f"  403 Forbidden {url[:60]} (可能被反爬拦截)")
                # 换一个浏览器指纹重试
                global _current_profile
                _current_profile = None
                if attempt < retries:
                    time.sleep(random.uniform(3, 6))
                    continue
            elif status == 429:
                log.warning(f"  429 Rate limited {url[:60]}")
                if attempt < retries:
                    time.sleep(random.uniform(5, 10))
                    continue
            elif status == 406:
                log.warning(f"  406 Not Acceptable {url[:60]}")
                _current_profile = None
                if attempt < retries:
                    time.sleep(random.uniform(2, 4))
                    continue
            else:
                log.warning(f"  HTTP {status} {url[:60]}")
            return None
        except Exception as e:
            log.warning(f"  抓取失败 {url[:60]}: {e}")
            if attempt < retries:
                time.sleep(random.uniform(1, 3))
                continue
            return None
    return None

def soup_of(url: str):
    html = fetch(url)
    return BeautifulSoup(html, "html.parser") if html else None

# ============================================================
# 日期解析
# ============================================================
def parse_dt(text: str) -> Optional[datetime]:
    if not text:
        return None
    text = text.strip()
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]:
        try:
            return datetime.strptime(text[:len(fmt)+2], fmt)
        except (ValueError, IndexError):
            pass
    norm = re.sub(r"[年月/]", "-", text).replace("日", "").strip()
    norm = re.sub(r"\s+", " ", norm)
    try:
        return datetime.strptime(norm[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        pass
    try:
        return datetime.strptime(norm[:10], "%Y-%m-%d")
    except ValueError:
        pass
    m = re.search(r"(\d+)\s*分钟前", text)
    if m:
        return datetime.now() - timedelta(minutes=int(m.group(1)))
    m = re.search(r"(\d+)\s*小时前", text)
    if m:
        return datetime.now() - timedelta(hours=int(m.group(1)))
    if "刚刚" in text or "刚才" in text:
        return datetime.now()
    if "今天" in text:
        hm = re.search(r"(\d{1,2}):(\d{2})", text)
        if hm:
            now = datetime.now()
            return now.replace(hour=int(hm.group(1)), minute=int(hm.group(2)), second=0, microsecond=0)
    if "昨天" in text:
        hm = re.search(r"(\d{1,2}):(\d{2})", text)
        if hm:
            y = datetime.now() - timedelta(days=1)
            return y.replace(hour=int(hm.group(1)), minute=int(hm.group(2)), second=0, microsecond=0)
    return None

# ============================================================
# 22 个网站爬虫
# ============================================================
NAV_BLACKLIST = {'english', 'skip to main content', 'back to home',
                 'promotion', '登录', '注册', '首页', '更多',
                 'english version', '网上有害信息举报专区'}

def scrape_page_links(soup, base_url: str, name: str) -> List[Dict]:
    items = []
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        title = a.get_text(strip=True)
        if not title or len(title) < 6:
            continue
        if title.lower() in NAV_BLACKLIST:
            continue
        if len(title) < 8 and not any(c.isdigit() for c in title):
            continue
        if not href.startswith("http"):
            href = base_url.rstrip("/") + "/" + href.lstrip("/")
        dt = None
        parent = a.find_parent(["li", "div", "tr", "article"])
        if parent:
            for cls_pat in [r"time", r"date", r"stamp"]:
                el = parent.find(class_=re.compile(cls_pat, re.I))
                if el:
                    dt = parse_dt(el.get_text())
                    if dt:
                        break
        items.append({"source": name, "title": title, "url": href, "publish_time": dt, "summary": ""})
    return items

def scrape_wallstreetcn(name):
    items = []
    for api in [
        "https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&limit=50",
        "https://api-one.wallstcn.com/apiv1/content/articles?channel=global-channel&limit=30",
    ]:
        text = fetch(api)
        if not text:
            continue
        try:
            data = json.loads(text)
            for it in data.get("data", {}).get("items", []):
                title = it.get("title", "") or it.get("content_text", "")
                if not title:
                    continue
                ts = it.get("display_time", 0)
                dt = datetime.fromtimestamp(ts) if ts > 1e9 else None
                nid = it.get("id", "")
                uri = it.get("uri", "")
                url = f"https://wallstreetcn.com/live/{nid}" if "live" in api else f"https://wallstreetcn.com/articles/{uri}"
                items.append({"source": name, "title": title[:200], "url": url, "publish_time": dt, "summary": it.get("content_text", "")[:200]})
        except Exception:
            pass
    return items

def scrape_sina(name):
    text = fetch("https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=50&page=1")
    if not text:
        return []
    try:
        data = json.loads(text)
        items = []
        for it in data.get("result", {}).get("data", []):
            title = it.get("title", "")
            if not title:
                continue
            ts = int(it.get("ctime", it.get("intime", 0)))
            dt = datetime.fromtimestamp(ts) if ts > 1e9 else None
            items.append({"source": name, "title": title, "url": it.get("url", ""), "publish_time": dt, "summary": it.get("summary", "")[:200]})
        return items
    except Exception:
        return []

def scrape_cls(name):
    items = []
    for api in [
        'https://www.cls.cn/nodeapi/updateTelegraphList?app=CailianpressWeb&os=web&sv=8.4.6',
    ]:
        text = fetch(api)
        if not text:
            continue
        try:
            data = json.loads(text)
            roll = data.get("data", {}).get("roll_data", data.get("data", {}).get("roll_list", []))
            for it in roll:
                title = it.get("title", "") or it.get("brief", "")
                if not title:
                    continue
                ts = it.get("ctime", 0)
                dt = datetime.fromtimestamp(ts) if ts > 1e9 else None
                nid = it.get("id", "")
                url = f"https://www.cls.cn/detail/{nid}" if nid else ""
                items.append({"source": name, "title": title, "url": url, "publish_time": dt, "summary": it.get("brief", "")[:200]})
        except Exception:
            pass
    return items

def scrape_36kr(name):
    items = []
    for api in [
        'https://gateway.36kr.com/api/mis/nav/home/nav/rank/hot',
    ]:
        text = fetch(api)
        if not text:
            continue
        try:
            data = json.loads(text)
            hot = data.get('data', {}).get('hotRankList', [])
            flow = data.get('data', {}).get('itemList', [])
            for it in (hot or flow):
                mat = it.get("templateMaterial", {})
                title = mat.get("widgetTitle", it.get("title", ""))
                if not title:
                    continue
                item_id = it.get("itemId", it.get("id", ""))
                url = f"https://www.36kr.com/p/{item_id}" if item_id else ""
                items.append({"source": name, "title": title, "url": url, "publish_time": None, "summary": mat.get("widgetContent", "")[:200]})
        except Exception:
            pass
    return items

def scrape_huxiu(name):
    text = fetch("https://api-article.huxiu.com/web/article/list")
    if not text:
        return []
    try:
        data = json.loads(text)
        items = []
        for a in data.get("data", {}).get("datalist", []):
            title = a.get("title", "")
            if not title:
                continue
            aid = a.get("aid", a.get("id", ""))
            ts = a.get("dateline", 0)
            dt = datetime.fromtimestamp(ts) if ts > 1e9 else None
            items.append({"source": name, "title": title, "url": f"https://www.huxiu.com/article/{aid}.html", "publish_time": dt, "summary": a.get("summary", "")[:200]})
        return items
    except Exception:
        return []

def scrape_techcrunch(name):
    html = fetch("https://techcrunch.com/feed/")
    if not html:
        return []
    try:
        soup = BeautifulSoup(html, "lxml-xml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    items = []
    for item in soup.find_all("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate") or item.find("pubdate")
        desc_el = item.find("description")
        title = title_el.get_text(strip=True) if title_el else ""
        url = link_el.get_text(strip=True) if link_el else ""
        dt = None
        if pub_el:
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(pub_el.get_text(strip=True)).replace(tzinfo=None)
            except Exception:
                pass
        summary = desc_el.get_text(strip=True)[:200] if desc_el else ""
        if title:
            items.append({"source": name, "title": title, "url": url, "publish_time": dt, "summary": summary})
    return items

def scrape_tradingeconomics(name):
    soup = soup_of("https://tradingeconomics.com/news")
    if not soup:
        return []
    items = []
    for a in soup.select("a[href*='/news/']"):
        title = a.get_text(strip=True)
        if not title or len(title) < 10:
            continue
        href = a.get("href", "")
        if not href.startswith("http"):
            href = "https://tradingeconomics.com" + href
        dt = None
        parent = a.find_parent(["tr", "li", "div"])
        if parent:
            for td in parent.find_all("td"):
                dt = parse_dt(td.get_text())
                if dt:
                    break
        items.append({"source": name, "title": title, "url": href, "publish_time": dt, "summary": ""})
    return items

def scrape_site(site: dict) -> List[Dict]:
    name, url, stype = site["name"], site["url"], site["type"]
    if stype == "wallstreetcn": return scrape_wallstreetcn(name)
    if stype == "sina": return scrape_sina(name)
    if stype == "cls": return scrape_cls(name)
    if stype == "kr36": return scrape_36kr(name)
    if stype == "huxiu": return scrape_huxiu(name)
    if stype == "techcrunch": return scrape_techcrunch(name)
    if stype == "tradingeconomics": return scrape_tradingeconomics(name)
    soup = soup_of(url)
    if not soup: return []
    items = scrape_page_links(soup, url, name)
    extra_pages = {
        "ce": ["http://finance.ce.cn/", "http://www.ce.cn/xwzx/gnsz/gdxw/index.shtml"],
        "yicai": ["https://www.yicai.com/news/"],
        "cnfin": ["https://www.cnfin.com/xhsczx/index.html"],
        "ndrc": ["https://www.ndrc.gov.cn/xwdt/xwfb/index.html", "https://www.ndrc.gov.cn/xxgk/zcfb/index.html"],
        "mof": ["https://www.mof.gov.cn/zhengwuxinxi/caizhengxinwen/"],
        "pbc": ["https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html"],
        "fed": ["https://www.federalreserve.gov/newsevents.htm"],
    }
    for ep in extra_pages.get(stype, []):
        human_delay()
        s2 = soup_of(ep)
        if s2:
            items.extend(scrape_page_links(s2, ep, name))
    return items

# ============================================================
# TF-IDF 粗筛去重
# ============================================================
def tokenize(text: str) -> List[str]:
    text = re.sub(r"[^\u4e00-\u9fffa-zA-Z0-9]", " ", text)
    return [w.strip() for w in jieba.cut(text) if len(w.strip()) > 1]

def cosine_sim(a: List[str], b: List[str]) -> float:
    if not a or not b:
        return 0.0
    fa, fb = defaultdict(int), defaultdict(int)
    for t in a: fa[t] += 1
    for t in b: fb[t] += 1
    common = set(fa) & set(fb)
    if not common:
        return 0.0
    dot = sum(fa[k] * fb[k] for k in common)
    return dot / ((sum(v*v for v in fa.values())**0.5) * (sum(v*v for v in fb.values())**0.5))

def rough_dedup(items: List[Dict]) -> List[Dict]:
    """TF-IDF 粗筛：去掉字面高度相似的重复项"""
    if not items:
        return []
    tokens = [tokenize(it.get("title","") + " " + it.get("summary","")) for it in items]
    n = len(items)
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for i in range(n):
        for j in range(i+1, n):
            if cosine_sim(tokens[i], tokens[j]) >= SIM_THRESHOLD:
                union(i, j)

    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)

    merged = []
    for g, indices in groups.items():
        group = [items[i] for i in indices]
        official = [it for it in group if it["source"] in OFFICIAL]
        if official:
            best = official[0]
        else:
            group.sort(key=lambda x: x.get("publish_time") or datetime.max)
            best = group[0]
        best["group_size"] = len(indices)
        merged.append(best)

    merged.sort(key=lambda x: x.get("publish_time") or datetime.min, reverse=True)
    return merged

# ============================================================
# 主流程
# ============================================================
def main():
    script_start = time.time()
    now = datetime.now()
    today_8am = now.replace(hour=8, minute=0, second=0, microsecond=0)
    if now < today_8am:
        today_8am -= timedelta(days=1)
    start = today_8am - timedelta(days=1)
    end = today_8am
    date_str = today_8am.strftime("%Y-%m-%d")

    log.info(f"采集窗口: {start} ~ {end}")
    log.info(f"浏览器指纹: {_pick_profile()['ua'][:50]}...")

    all_items = []
    for i, site in enumerate(SITES):
        log.info(f"[{i+1}/{len(SITES)}] 抓取: {site['name']}")
        try:
            items = scrape_site(site)
            valid, no_time = [], []
            for it in items:
                if not it.get("title") or len(it["title"]) < 5:
                    continue
                dt = it.get("publish_time")
                if dt and start <= dt < end:
                    valid.append(it)
                elif dt is None:
                    no_time.append(it)
            remaining = MAX_PER_SITE - len(valid)
            if remaining > 0 and no_time:
                mid = start + (end - start) / 2
                for it in no_time[:remaining]:
                    it["publish_time"] = mid
                    valid.append(it)
            valid.sort(key=lambda x: x.get("publish_time") or datetime.min, reverse=True)
            result = valid[:MAX_PER_SITE]
            all_items.extend(result)
            log.info(f"  获取 {len(items)} 条, 保留 {len(result)} 条")
        except Exception as e:
            log.error(f"  [{site['name']}] 异常: {e}")
        # 站间随机延迟
        human_delay()

    # TF-IDF 粗筛
    log.info(f"总计 {len(all_items)} 条, TF-IDF 粗筛去重...")
    merged = rough_dedup(all_items)
    log.info(f"粗筛后 {len(merged)} 条 (去除 {len(all_items)-len(merged)} 条字面重复)")

    for it in merged:
        if it.get("publish_time") and isinstance(it["publish_time"], datetime):
            it["publish_time"] = it["publish_time"].strftime("%Y-%m-%d %H:%M")
        else:
            it["publish_time"] = ""

    output = {
        "date": date_str,
        "window": f"{start.strftime('%Y-%m-%d %H:%M')} ~ {end.strftime('%Y-%m-%d %H:%M')}",
        "total_scraped": len(all_items),
        "total_after_tfidf": len(merged),
        "script_seconds": round(time.time() - script_start, 1),
        "news": merged,
    }
    out_dir = os.path.expanduser(f"~/financial-news-daily/output/{date_str}")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"raw_data_{date_str}.json"), "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 关闭连接池
    if _client:
        _client.close()

    # 输出 JSON 到 stdout（唯一输出，确保干净）
    # 清除所有 U+FEFF (BOM) 字符，避免触发 cron 注入扫描器
    def _strip_bom(obj):
        if isinstance(obj, str):
            return obj.replace('\ufeff', '')
        if isinstance(obj, list):
            return [_strip_bom(i) for i in obj]
        if isinstance(obj, dict):
            return {k: _strip_bom(v) for k, v in obj.items()}
        return obj
    output = _strip_bom(output)
    json_str = json.dumps(output, ensure_ascii=False)
    sys.stdout.write(json_str)
    sys.stdout.flush()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # 被中断时输出空结果，避免 agent 收到空上下文
        print('{"date":"","window":"","total_scraped":0,"total_after_tfidf":0,"news":[]}')
        sys.exit(0)
