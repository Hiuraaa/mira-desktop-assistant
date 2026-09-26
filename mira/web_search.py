"""Small, free web lookup with sources. Search snippets are untrusted data."""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from html.parser import HTMLParser


def local_time() -> str:
    now = datetime.now().astimezone()
    return "Giờ trên máy tính: " + now.strftime("%Y-%m-%d %H:%M:%S %Z (%z)")


class _Results(HTMLParser):
    """Read visible titles and snippets from DuckDuckGo's HTML results."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self.current: dict[str, str] | None = None
        self.field = ""
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if self.field:
            if tag not in ("br", "img", "input", "meta", "link", "hr"):
                self.depth += 1
            return
        if tag == "a" and "result__a" in classes:
            if self.current:
                self.results.append(self.current)
            self.current = {"url": attrs.get("href", ""), "title": "", "snippet": ""}
            self.field = "title"
        elif self.current and "result__snippet" in classes:
            self.field = "snippet"
        else:
            return
        self.depth = 1
        self.parts = []

    def handle_data(self, data):
        if self.field:
            self.parts.append(data)

    def handle_startendtag(self, tag, attrs):
        # Void tags inside a snippet do not add a closing level.
        return

    def handle_endtag(self, tag):
        if not self.field:
            return
        self.depth -= 1
        if not self.depth:
            if self.current:
                self.current[self.field] = " ".join("".join(self.parts).split())
            self.field = ""

    def finish(self):
        if self.current:
            self.results.append(self.current)
        return self.results


def _result_url(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlparse(href)
    if (parsed.hostname == "duckduckgo.com" or
            (parsed.hostname or "").endswith(".duckduckgo.com")) and parsed.path.startswith("/l/"):
        href = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
        parsed = urllib.parse.urlparse(href)
    return href if parsed.scheme in ("http", "https") and parsed.hostname else ""


def _read(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "MiraDesktopAssistant/1.0 (personal search)"})
    with urllib.request.urlopen(request, timeout=12) as response:
        return response.read(512_000)


def search_web(query: str) -> str:
    if not isinstance(query, str) or not query.strip() or len(query.strip()) > 180:
        raise ValueError("Câu tìm kiếm phải dài từ 1 đến 180 ký tự.")
    query = query.strip()
    encoded = urllib.parse.urlencode({"q": query})
    results: list[dict[str, str]] = []
    try:
        parser = _Results()
        parser.feed(_read("https://html.duckduckgo.com/html/?" + encoded).decode("utf-8", "replace"))
        results = parser.finish()
    except (OSError, ValueError):
        pass
    valid = [(item["title"][:180], _result_url(item["url"]), item["snippet"][:400])
             for item in results if item["title"] and _result_url(item["url"])]
    if valid:
        lines = ["Kết quả DuckDuckGo (chỉ tiêu đề và trích đoạn; chưa đọc toàn bài):"]
        for number, (title, url, snippet) in enumerate(valid[:5], 1):
            lines.append(f"{number}. {title}\nURL: {url}\nTrích đoạn: {snippet or '(không có)'}")
        return "\n".join(lines)

    # The HTML endpoint sometimes rate-limits automation. Fall back to a
    # clearly labelled encyclopedia search instead of pretending to browse.
    for language in ("vi", "en"):
        url = f"https://{language}.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query", "list": "search", "srsearch": query,
            "srlimit": 4, "format": "json", "formatversion": 2,
        })
        try:
            entries = json.loads(_read(url)).get("query", {}).get("search", [])
        except (OSError, ValueError, TypeError):
            continue
        if entries:
            lines = [f"Chỉ tìm được Wikipedia ({language}); chưa có kết quả tìm web rộng hoặc tin mới:"]
            for number, item in enumerate(entries[:4], 1):
                title = str(item.get("title", ""))[:180]
                link = f"https://{language}.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
                snippet = html.unescape(re.sub(r"<[^>]*>", "", str(item.get("snippet", ""))))[:400]
                lines.append(f"{number}. {title}\nURL: {link}\nTrích đoạn: {snippet}")
            return "\n".join(lines)
    return "Không tìm được kết quả đáng tin cậy lúc này. Hãy nói rõ rằng việc tra cứu chưa thành công."
