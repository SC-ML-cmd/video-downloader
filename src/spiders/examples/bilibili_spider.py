"""B站爬虫示例 — 演示如何为特定网站定制爬虫

注意：B站视频通常需要 cookies 才能获取高清画质。
可以通过浏览器登录后导出 cookies.txt 文件。

使用 yt-dlp 内置的 BiliBili 提取器，本示例展示如何包装它。
"""
from pathlib import Path
from typing import Optional

import yt_dlp

from ..base_spider import BaseSpider


class BilibiliSpider(BaseSpider):
    """B站视频爬虫"""

    name = "bilibili"
    domain = "bilibili.com"

    def can_handle(self, url: str) -> bool:
        return "bilibili.com/video/" in url or "b23.tv" in url

    def extract_info(self, url: str) -> dict:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }
        if self.proxy:
            ydl_opts["proxy"] = self.proxy
        if self.cookies_file:
            ydl_opts["cookiefile"] = self.cookies_file

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info

    def download(self, url: str, output_dir: str,
                 quality: Optional[str] = None) -> str:
        quality_fmt = {
            "4K": "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
            "1080p60": "bestvideo[height<=1080][fps>30]+bestaudio/"
                       "best[height<=1080]",
            "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
        }

        fmt = quality_fmt.get(quality, "bestvideo+bestaudio/best")

        outtmpl = str(Path(output_dir) / "%(title)s-%(id)s.%(ext)s")
        ydl_opts = {
            "format": fmt,
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
            "noplaylist": True,
        }

        if self.proxy:
            ydl_opts["proxy"] = self.proxy
        if self.cookies_file:
            ydl_opts["cookiefile"] = self.cookies_file

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename


def test_bilibili():
    """B站爬虫测试"""
    spider = BilibiliSpider()

    # B站视频
    url = "https://www.bilibili.com/video/BV1ULf8YnEXQ/"

    print(f"测试: {url}")
    print(f"可处理: {spider.can_handle(url)}")

    if spider.can_handle(url):
        info = spider.extract_info(url)
        print(f"标题: {info.get('title')}")
        print(f"时长: {info.get('duration')}s")
        print(f"作者: {info.get('uploader')}")
        fmt_count = len(info.get("formats", []))
        print(f"可用格式: {fmt_count} 个")
        for f in info.get("formats", [])[:5]:
            print(f"  - {f.get('format_id')}: {f.get('resolution')} "
                  f"({f.get('ext')})")


if __name__ == "__main__":
    test_bilibili()
