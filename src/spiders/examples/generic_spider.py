"""通用爬虫 — 适用于 yt-dlp 不支持或已封禁的网站

策略:
  1. strencode2 解码提取的 URL → 最高优先级（包含完整音视频）
  2. HTML 注释中的备用 URL → 中优先级
  3. 正则匹配到的其他 mp4/m3u8 链接 → 低优先级
  4. 用 requests 直接下载（绕过 yt-dlp）
"""
import re
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from ..base_spider import BaseSpider
from ...stream_parser import detect_stream_type
from ...downloader import download_direct, DirectDownloadProgress
from ...utils import sanitize_filename


class GenericSpider(BaseSpider):
    """通用网页视频爬虫 — 分析 HTML 提取视频资源并直接下载"""

    name = "generic"
    domain = "*"

    def __init__(self, proxy: Optional[str] = None,
                 cookies_file: Optional[str] = None):
        super().__init__(proxy, cookies_file)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        })
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

    def can_handle(self, url: str) -> bool:
        return True

    # ========== 信息提取 ==========

    def extract_info(self, url: str) -> dict:
        """提取网页中的视频资源信息"""
        result = {
            "url": url,
            "title": "",
            "videos": [],
            "streams": [],
            "iframes": [],
        }

        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        result["title"] = self._extract_title(soup)
        result["videos"] = self._extract_video_tags(soup, url)
        result["streams"] = self._extract_stream_urls(resp.text, url)
        result["iframes"] = self._extract_iframes(soup, url)

        return result

    def extract_best_video_url(self, url: str) -> Optional[str]:
        """
        从页面提取最佳视频下载 URL。

        优先级:
          1. strencode2 解码 → 完整音视频
          2. HTML 注释中的备用 mp4
          3. 其他 mp4 链接
        """
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        html = resp.text

        # P1: strencode2 解码
        video_url = self._decode_strencode(html)
        if video_url:
            return video_url

        # P2: HTML 注释中的 mp4
        commented = re.search(
            r"<!--\s*<source\s+src=['\"](https?://[^'\"]+\.mp4\?[^'\"]+)['\"]",
            html
        )
        if commented:
            return commented.group(1)

        # P3: 直接匹配 mp4 链接
        all_mp4 = re.findall(
            r'https?://[^"\'<>\s]+\.mp4\?[^"\'<>\s]+',
            html
        )
        # 过滤掉注释中的
        live_mp4s = [u for u in all_mp4 if f"<!-- {u}" not in html]
        if live_mp4s:
            return live_mp4s[0]

        return None

    def extract_title_from_page(self, url: str) -> str:
        """仅提取页面标题"""
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        return self._extract_title(soup)

    # ========== 下载 ==========

    def download(self, url: str, output_dir: str,
                 quality: Optional[str] = None) -> str:
        """
        智能下载：先尝试 yt-dlp，失败则用蜘蛛提取 + 直接下载
        """
        # 1. 尝试 yt-dlp
        try:
            import yt_dlp
            outtmpl = str(Path(output_dir) / "%(title)s-%(id)s.%(ext)s")
            ydl_opts = {
                "outtmpl": outtmpl,
                "noplaylist": True,
            }
            if self.proxy:
                ydl_opts["proxy"] = self.proxy
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)
        except Exception:
            pass  # yt-dlp 失败，降级到蜘蛛模式

        # 2. 蜘蛛提取 + 直接下载
        return self.download_from_page(url, output_dir)

    def download_from_page(
        self, url: str, output_dir: str, filename: Optional[str] = None
    ) -> str:
        """
        从页面提取视频 URL 并直接下载（仅一次 HTTP 请求解析页面）。

        自动处理 strencode2 解码、Referer 头等。
        """
        # 一次请求获取页面 HTML
        resp = self.session.get(url, timeout=30,
                                proxies={"http": None, "https": None})
        resp.raise_for_status()
        html = resp.text

        # 从同一份 HTML 中提取视频 URL 和标题
        video_url = self._decode_strencode(html)
        if not video_url:
            video_url = self.extract_best_video_url(url)

        if not video_url:
            raise ValueError(f"未能从页面提取到视频链接: {url}")

        soup = BeautifulSoup(html, "html.parser")
        title = self._extract_title(soup)

        if filename is None:
            filename = sanitize_filename(title)

        parsed = urllib.parse.urlparse(url)
        referer = f"{parsed.scheme}://{parsed.netloc}/"

        print(f"  视频 URL: {video_url[:100]}...")
        print(f"  Referer: {referer}")

        progress = DirectDownloadProgress("下载")
        filepath = download_direct(
            video_url=video_url,
            output_dir=output_dir,
            filename=filename,
            referer=referer,
            progress=progress,
            session=self.session,
        )
        return filepath

    # ========== 内部方法 ==========

    def _decode_strencode(self, html: str) -> Optional[str]:
        """
        解码 strencode2 / strencode 混淆的视频 URL。

        strencode2 = unescape (简单 URL 解码)
        strencode  = XOR + base64 (复杂解码，需要特定 key)
        """
        # strencode2: document.write(strencode2("%3c%73..."))
        for m in re.finditer(
            r"strencode2\(\s*['\"]([^'\"]+)['\"]\s*\)", html
        ):
            try:
                decoded = urllib.parse.unquote(m.group(1))
                src_m = re.search(r"src=['\"]([^'\"]+)['\"]", decoded)
                if src_m and src_m.group(1).startswith("http"):
                    return src_m.group(1)
            except Exception:
                pass

        # strencode: 3参数版本（XOR 解码，存在于 m.js）
        # 这种形式的解码需要知道 key，通常 key 也在页面内
        for m in re.finditer(
            r"strencode\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)",
            html
        ):
            try:
                import base64
                encoded = m.group(1)
                key = m.group(3)
                decoded_bytes = base64.b64decode(encoded)
                key_bytes = key.encode("utf-8")
                result = ""
                for i, b in enumerate(decoded_bytes):
                    result += chr(b ^ key_bytes[i % len(key_bytes)])
                return result
            except Exception:
                pass

        return None

    def _extract_title(self, soup) -> str:
        """从网页提取标题"""
        for tag in ["og:title", "twitter:title"]:
            meta = (soup.find("meta", property=tag) or
                    soup.find("meta", attrs={"name": tag}))
            if meta and meta.get("content"):
                return meta["content"].strip()

        title_tag = soup.find("title")
        if title_tag and title_tag.text.strip():
            # 去掉站点后缀
            title = title_tag.text.strip()
            title = re.sub(r"\s*[-|]\s*\w+porn.*$", "", title, flags=re.I)
            return title
        return f"video_{int(time.time())}"

    def _extract_video_tags(self, soup, base_url: str) -> list:
        """提取 <video> 标签及其 <source> 子元素"""
        videos = []
        for video_tag in soup.find_all("video"):
            sources = []
            for src in video_tag.find_all("source"):
                src_url = src.get("src", "")
                if src_url:
                    sources.append({
                        "url": urllib.parse.urljoin(base_url, src_url),
                        "type": src.get("type", ""),
                        "stream_type": detect_stream_type(
                            urllib.parse.urljoin(base_url, src_url)
                        ),
                    })
            direct_src = video_tag.get("src", "")
            if direct_src:
                sources.append({
                    "url": urllib.parse.urljoin(base_url, direct_src),
                    "type": "",
                    "stream_type": detect_stream_type(
                        urllib.parse.urljoin(base_url, direct_src)
                    ),
                })
            if sources:
                videos.append({"tag_id": video_tag.get("id", ""),
                              "sources": sources})
        return videos

    def _extract_stream_urls(self, html: str, base_url: str) -> list:
        """从 HTML/JS 中提取所有流媒体链接"""
        streams = []

        # P1: strencode2 解码的 URL（最高优先级，确保排在前面）
        strencode_url = self._decode_strencode(html)
        if strencode_url:
            streams.append({
                "url": strencode_url,
                "type": "direct",
                "priority": "high",
                "source": "strencode2",
            })

        # P2: 其他流媒体链接
        patterns = [
            (r'(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)', "hls"),
            (r'(https?://[^"\'<>\s]+\.mpd[^"\'<>\s]*)', "dash"),
            (r'(https?://[^"\'<>\s]+\.mp4\?[^"\'<>\s]+)', "direct"),
        ]

        seen = {strencode_url} if strencode_url else set()
        for pattern, stype in patterns:
            for match in re.finditer(pattern, html):
                u = match.group(1).rstrip(",\\")
                if u not in seen:
                    seen.add(u)
                    streams.append({
                        "url": u,
                        "type": stype,
                        "priority": "normal",
                    })

        return streams

    def _extract_iframes(self, soup, base_url: str) -> list:
        """提取 iframe 链接"""
        iframes = []
        for iframe in soup.find_all("iframe"):
            src = iframe.get("src", "")
            if src:
                iframes.append({
                    "url": urllib.parse.urljoin(base_url, src),
                    "title": iframe.get("title", ""),
                })
        return iframes
