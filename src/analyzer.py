"""视频分析器 — 分析网页中的视频资源"""
from typing import Optional

import yt_dlp

from .utils import format_size, format_duration


class VideoInfo:
    """视频信息数据类"""
    def __init__(self, info: dict):
        self.title: str = info.get("title", "未知标题")
        self.url: str = info.get("webpage_url", "")
        self.duration: Optional[int] = info.get("duration")
        self.view_count: Optional[int] = info.get("view_count")
        self.like_count: Optional[int] = info.get("like_count")
        self.upload_date: Optional[str] = info.get("upload_date")
        self.uploader: Optional[str] = info.get("uploader")
        self.description: str = (info.get("description") or "")[:200]
        self.formats: list[dict] = info.get("formats", [])
        self.thumbnail: Optional[str] = info.get("thumbnail")

        # 提取唯一格式
        self.unique_formats = self._extract_unique_formats()

    def _extract_unique_formats(self) -> list[dict]:
        """提取不重复的格式列表，按质量排序"""
        seen = set()
        unique = []
        for fmt in self.formats:
            key = (fmt.get("format_note", ""),
                   fmt.get("ext", ""),
                   fmt.get("resolution", ""))
            if key not in seen:
                seen.add(key)
                unique.append(fmt)

        # 按高度降序排列
        unique.sort(
            key=lambda f: (f.get("height") or 0),
            reverse=True,
        )
        return unique

    def get_summary(self) -> str:
        """生成格式化的视频信息摘要"""
        lines = []
        lines.append("=" * 60)
        lines.append(f"  标题: {self.title}")
        lines.append(f"  时长: {format_duration(self.duration)}")
        if self.uploader:
            lines.append(f"  作者: {self.uploader}")
        if self.upload_date:
            date_str = self.upload_date
            formatted_date = (f"{date_str[:4]}-{date_str[4:6]}-"
                              f"{date_str[6:8]}")
            lines.append(f"  日期: {formatted_date}")
        if self.view_count:
            lines.append(f"  播放: {self.view_count:,}")
        if self.description:
            lines.append(f"  简介: {self.description[:100]}...")
        lines.append("=" * 60)
        lines.append(f"  可用格式数: {len(self.unique_formats)}")
        lines.append("-" * 60)

        for i, fmt in enumerate(self.unique_formats):
            fmt_id = fmt.get("format_id", "?")
            ext = fmt.get("ext", "?")
            res = fmt.get("resolution", "仅音频" if
                          fmt.get("acodec") != "none" and
                          fmt.get("vcodec") == "none" else "?")
            filesize = format_size(fmt.get("filesize") or
                                   fmt.get("filesize_approx"))
            tbr = fmt.get("tbr", 0)
            vcodec = fmt.get("vcodec", "?")
            acodec = fmt.get("acodec", "?")
            note = fmt.get("format_note", "")

            audio_only = fmt.get("acodec") != "none" and \
                         fmt.get("vcodec") == "none"

            type_tag = "[音频]" if audio_only else "[视频]"
            lines.append(
                f"  {i+1:2d}. [{fmt_id:>6s}] {type_tag} {res:>10s}  "
                f"{ext:>5s}  {filesize:>10s}  "
                f"{tbr:>6.0f}kbps  "
                f"{note:>8s}"
            )
        lines.append("-" * 60)
        return "\n".join(lines)


def analyze_video(
    url: str,
    proxy: Optional[str] = None,
    cookies_file: Optional[str] = None,
    headers: Optional[dict] = None,
) -> VideoInfo:
    """
    分析视频 URL，提取元数据。

    Args:
        url: 视频页面 URL
        proxy: 代理地址
        cookies_file: cookies 文件路径
        headers: 自定义 HTTP 头

    Returns:
        VideoInfo 对象
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }

    if proxy:
        ydl_opts["proxy"] = proxy
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file
    if headers:
        ydl_opts["http_headers"] = headers

    ydl_opts["http_headers"] = {
        **ydl_opts.get("http_headers", {}),
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            raise ValueError(f"无法解析视频: {url}")
        return VideoInfo(info)


def list_formats(
    url: str,
    proxy: Optional[str] = None,
    cookies_file: Optional[str] = None,
) -> VideoInfo:
    """列出视频的所有可用格式（同 analyze_video 但更侧重格式信息）"""
    return analyze_video(url, proxy=proxy, cookies_file=cookies_file)
