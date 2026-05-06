"""流媒体解析器 — 解析 HLS (m3u8) 和 DASH (mpd) 播放列表"""
import re
from typing import Optional
from urllib.parse import urljoin

import requests
import m3u8


class StreamInfo:
    """流媒体信息"""
    def __init__(self, url: str, bandwidth: int = 0, resolution: str = "",
                 codecs: str = "", frame_rate: float = 0.0,
                 media_type: str = "video"):
        self.url = url
        self.bandwidth = bandwidth  # bps
        self.resolution = resolution  # e.g. "1920x1080"
        self.codecs = codecs
        self.frame_rate = frame_rate
        self.media_type = media_type  # "video" or "audio"

    @property
    def bandwidth_mbps(self) -> float:
        return self.bandwidth / 1_000_000

    def __repr__(self):
        if self.media_type == "video":
            return (f"VideoStream({self.resolution}, "
                    f"{self.bandwidth_mbps:.1f}Mbps, {self.codecs})")
        return f"AudioStream({self.bandwidth_mbps:.2f}Mbps, {self.codecs})"


def parse_m3u8(url: str, headers: Optional[dict] = None) -> list[StreamInfo]:
    """解析 m3u8 播放列表，返回所有可用的流"""
    if headers is None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        }

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    playlist = m3u8.loads(resp.text)

    streams = []

    if playlist.is_variant:
        # 多码率播放列表
        for pl in playlist.playlists:
            stream_url = pl.absolute_uri or urljoin(url, pl.uri)
            resolution = ""
            if pl.stream_info.resolution:
                resolution = (f"{pl.stream_info.resolution[0]}x"
                              f"{pl.stream_info.resolution[1]}")
            frame_rate = pl.stream_info.frame_rate or 0.0

            streams.append(StreamInfo(
                url=stream_url,
                bandwidth=pl.stream_info.bandwidth or 0,
                resolution=resolution,
                codecs=pl.stream_info.codecs or "",
                frame_rate=frame_rate,
                media_type="video",
            ))

            # 音频轨道
            for alt in playlist.media or []:
                if alt.type == "AUDIO":
                    audio_url = alt.absolute_uri or urljoin(url, alt.uri)
                    streams.append(StreamInfo(
                        url=audio_url,
                        bandwidth=0,
                        resolution="",
                        codecs=alt.language or "",
                        media_type="audio",
                    ))
    else:
        # 单一播放列表（通常是分片列表）
        total_duration = sum(seg.duration for seg in playlist.segments)
        streams.append(StreamInfo(
            url=url,
            bandwidth=0,
            resolution="",
            codecs=f"{len(playlist.segments)} segments, "
                   f"~{total_duration:.0f}s",
            media_type="video",
        ))

    return streams


def parse_mpd(url: str, headers: Optional[dict] = None) -> list[StreamInfo]:
    """解析 MPEG-DASH MPD manifest"""
    if headers is None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        }

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    content = resp.text

    streams = []

    # 解析 AdaptationSet / Representation
    rep_pattern = re.compile(
        r'<Representation[^>]*?id="([^"]*)"[^>]*?'
        r'bandwidth="(\d+)"[^>]*?(?:width="(\d+)"\s+height="(\d+)")?[^>]*?'
        r'(?:codecs="([^"]*)")?[^>]*?(?:frameRate="([^"]*)")?[^>]*?>',
        re.IGNORECASE
    )

    for match in rep_pattern.finditer(content):
        rep_id = match.group(1)
        bandwidth = int(match.group(2))
        width = match.group(3)
        height = match.group(4)
        codecs_str = match.group(5) or ""
        frame_rate_str = match.group(6) or "0"

        resolution = f"{width}x{height}" if width and height else ""
        try:
            frame_rate = float(frame_rate_str.split("/")[0])
        except (ValueError, IndexError):
            frame_rate = 0.0

        streams.append(StreamInfo(
            url=url + f"#representation={rep_id}",
            bandwidth=bandwidth,
            resolution=resolution,
            codecs=codecs_str,
            frame_rate=frame_rate,
            media_type="video",
        ))

    return streams


def detect_stream_type(url: str) -> str:
    """检测流媒体类型"""
    url_lower = url.lower()
    if ".m3u8" in url_lower:
        return "hls"
    if ".mpd" in url_lower or "/dash/" in url_lower:
        return "dash"
    if ".mp4" in url_lower or ".webm" in url_lower or ".flv" in url_lower:
        return "direct"
    return "unknown"
