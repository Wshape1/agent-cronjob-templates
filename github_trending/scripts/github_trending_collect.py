#!/usr/bin/env python3
"""
GitHub Trending 采集脚本
- 抓取近24小时最火仓库 (Top 10)
- 输出 JSON 到 stdout 供 agent 邮件格式化

依赖: httpx, beautifulsoup4
"""
import json
import os
import re
import sys
import time
import logging
from typing import List, Dict, Optional

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("gh-trending")

try:
    import httpx
    from bs4 import BeautifulSoup
except ImportError:
    VENV = os.path.expanduser("~/financial-news-daily/.venv/lib/python3.11/site-packages")
    if os.path.isdir(VENV):
        sys.path.insert(0, VENV)
        import httpx
        from bs4 import BeautifulSoup
    else:
        log.error("缺少依赖: pip install httpx beautifulsoup4")
        sys.exit(1)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

def fetch_trending() -> List[Dict]:
    """抓取 GitHub Trending 页面"""
    url = "https://github.com/trending?since=daily"
    log.info(f"抓取: {url}")
    try:
        client = httpx.Client(timeout=20, follow_redirects=True, verify=False)
        r = client.get(url, headers={
            "User-Agent": UA,
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.9",
        })
        r.raise_for_status()
        client.close()
    except Exception as e:
        log.error(f"抓取失败: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    repos = []

    # GitHub trending 的仓库在 article.Box-row 里
    for article in soup.select("article.Box-row"):
        try:
            # 仓库名
            h2 = article.select_one("h2 a")
            if not h2:
                continue
            href = h2.get("href", "").strip("/")
            parts = href.split("/")
            if len(parts) < 2:
                continue
            owner, name = parts[0], parts[1]
            full_name = f"{owner}/{name}"
            repo_url = f"https://github.com/{full_name}"

            # 描述
            desc_el = article.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else ""

            # 语言
            lang_el = article.select_one("[itemprop='programmingLanguage']")
            language = lang_el.get_text(strip=True) if lang_el else ""

            # 总 star 数
            star_links = article.select("a.Link--muted")
            total_stars = 0
            total_forks = 0
            for link in star_links:
                href_text = link.get("href", "")
                text = link.get_text(strip=True).replace(",", "")
                if "/stargazers" in href_text:
                    total_stars = int(text) if text.isdigit() else 0
                elif "/forks" in href_text:
                    total_forks = int(text) if text.isdigit() else 0

            # 今日 star
            today_stars = 0
            spans = article.select("span.d-inline-block.float-sm-right")
            for span in spans:
                m = re.search(r"([\d,]+)\s*stars?\s*today", span.get_text())
                if m:
                    today_stars = int(m.group(1).replace(",", ""))
                    break

            repos.append({
                "owner": owner,
                "name": name,
                "full_name": full_name,
                "url": repo_url,
                "description": description,
                "language": language,
                "total_stars": total_stars,
                "total_forks": total_forks,
                "today_stars": today_stars,
            })
        except Exception as e:
            log.warning(f"解析失败: {e}")
            continue

    log.info(f"获取 {len(repos)} 个仓库")
    return repos


def main():
    import datetime
    script_start = time.time()
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")

    repos = fetch_trending()

    # 取 Top 10
    top10 = repos[:10]

    output = {
        "date": date_str,
        "source": "GitHub Trending",
        "period": "近24小时",
        "total_fetched": len(repos),
        "script_seconds": round(time.time() - script_start, 1),
        "repos": top10,
    }

    # 保存到文件
    out_dir = os.path.expanduser(f"~/github-trending/output/{date_str}")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"trending_{date_str}.json"), "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
