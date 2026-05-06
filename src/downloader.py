"""视频下载器 — 基于 yt-dlp 的下载封装 + 直接 HTTP 下载"""
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional, Callable

# Windows 控制台 UTF-8 编码
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import requests
import yt_dlp

from .utils import find_ffmpeg, sanitize_filename


class DownloadProgress:
    """下载进度回调"""
    def __init__(self, label: str = "下载"):
        self.label = label

    def progress_hook(self, d: dict):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                percent = downloaded / total * 100
                speed = d.get("speed", 0)
                speed_str = self._fmt_speed(speed) if speed else "N/A"
                eta = d.get("eta", 0)
                eta_str = self._fmt_eta(eta) if eta else "N/A"
                bar_len = 30
                filled = int(bar_len * percent / 100)
                bar = "#" * filled + "-" * (bar_len - filled)
                print(f"\r[{self.label}] {bar} {percent:5.1f}% "
                      f"| {speed_str} | ETA: {eta_str}", end="")
                sys.stdout.flush()
        elif d["status"] == "finished":
            print(f"\r[{self.label}] 下载完成，正在处理...")
        elif d["status"] == "error":
            print(f"\r[{self.label}] 下载出错!")

    @staticmethod
    def _fmt_speed(speed: float) -> str:
        if speed > 1_000_000:
            return f"{speed / 1_000_000:.1f} MB/s"
        if speed > 1_000:
            return f"{speed / 1_000:.0f} KB/s"
        return f"{speed:.0f} B/s"

    @staticmethod
    def _fmt_eta(eta: int) -> str:
        if eta > 3600:
            return f"{eta // 3600}h{eta % 3600 // 60}m"
        if eta > 60:
            return f"{eta // 60}m{eta % 60}s"
        return f"{eta}s"


def download_video(
    url: str,
    output_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    format_str: str = "bestvideo+bestaudio/best",
    quality: Optional[str] = None,
    playlist: bool = False,
    proxy: Optional[str] = None,
    cookies_file: Optional[str] = None,
    headers: Optional[dict] = None,
    progress_hook: Optional[Callable] = None,
    quiet: bool = False,
    simulate: bool = False,
) -> dict:
    """
    使用 yt-dlp 下载视频。

    Args:
        url: 视频 URL
        output_path: 完整输出路径（包含文件名）
        output_dir: 输出目录
        format_str: 格式选择器
        quality: 画质简写（1080p, 720p, 480p 等），会转为对应的 format 选择器
        playlist: 是否下载播放列表
        proxy: 代理地址
        cookies_file: cookies 文件路径
        headers: 自定义 HTTP 头
        progress_hook: 进度回调
        quiet: 安静模式
        simulate: 仅模拟，不下载

    Returns:
        yt-dlp 的 info_dict
    """
    if output_dir is None:
        output_dir = str(Path.cwd() / "downloads")

    # 格式选择
    if quality:
        format_str = _quality_to_format(quality)

    outtmpl = str(Path(output_dir) / "%(title).100s-%(id)s.%(ext)s")
    if output_path:
        outtmpl = output_path

    ydl_opts = {
        "format": format_str,
        "outtmpl": outtmpl,
        "noplaylist": not playlist,
        "quiet": quiet,
        "no_warnings": quiet,
        "simulate": simulate,
        "merge_output_format": "mp4",
        "concurrent_fragment_downloads": 8,
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
        "progress_hooks": [progress_hook] if progress_hook else [],
    }

    # 自动检测 ffmpeg 路径
    ffmpeg_path = find_ffmpeg()
    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = ffmpeg_path
    else:
        # 没有 ffmpeg 时使用单文件格式（无需合并）
        ydl_opts["format"] = "best[ext=mp4]/best"
        ydl_opts.pop("merge_output_format", None)

    if proxy:
        ydl_opts["proxy"] = proxy

    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file

    if headers:
        ydl_opts["http_headers"] = headers

    # 添加通用请求头
    ydl_opts["http_headers"] = {
        **ydl_opts.get("http_headers", {}),
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=not simulate)


def _quality_to_format(quality: str) -> str:
    """将画质简写转为 yt-dlp 格式选择器"""
    quality_map = {
        "2160p": "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
        "1440p": "bestvideo[height<=1440]+bestaudio/best[height<=1440]",
        "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
        "best": "bestvideo+bestaudio/best",
        "worst": "worstvideo+worstaudio/worst",
    }
    return quality_map.get(quality, quality)


class DirectDownloadProgress:
    """直接 HTTP 下载的进度回调"""
    def __init__(self, label: str = "下载"):
        self.label = label
        self._last_update = 0

    def update(self, downloaded: int, total: int, speed: float = 0):
        now = time.time()
        if now - self._last_update < 0.2 and downloaded < total:
            return
        self._last_update = now

        if total > 0:
            percent = downloaded / total * 100
            bar_len = 30
            filled = int(bar_len * percent / 100)
            bar = "#" * filled + "-" * (bar_len - filled)

            if speed > 1_000_000:
                speed_str = f"{speed / 1_000_000:.1f} MB/s"
            elif speed > 1_000:
                speed_str = f"{speed / 1_000:.0f} KB/s"
            else:
                speed_str = f"{speed:.0f} B/s"

            if speed > 0:
                eta = (total - downloaded) / speed
                if eta > 3600:
                    eta_str = f"{eta // 3600:.0f}h{(eta % 3600) // 60:.0f}m"
                elif eta > 60:
                    eta_str = f"{eta // 60:.0f}m{eta % 60:.0f}s"
                else:
                    eta_str = f"{eta:.0f}s"
            else:
                eta_str = "N/A"

            print(f"\r[{self.label}] {bar} {percent:5.1f}% "
                  f"| {speed_str} | ETA: {eta_str}", end="")
            sys.stdout.flush()

    def done(self):
        print(f"\r[{self.label}] 下载完成" + " " * 50)


def download_direct(
    video_url: str,
    output_dir: str = "./downloads",
    filename: Optional[str] = None,
    referer: Optional[str] = None,
    progress: Optional[DirectDownloadProgress] = None,
    session: Optional[requests.Session] = None,
) -> str:
    """
    直接 HTTP 下载视频（不需要 yt-dlp）。

    Args:
        video_url: 视频直链 URL
        output_dir: 输出目录
        filename: 自定义文件名（不含扩展名）
        referer: Referer 请求头
        progress: 进度回调
        session: 复用已有的 requests.Session（保持 cookies/headers）

    Returns:
        下载文件路径
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if session is None:
        session = requests.Session()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if referer:
        headers["Referer"] = referer

    if progress is None:
        progress = DirectDownloadProgress()

    # 绕过系统代理，直连 CDN
    resp = session.get(video_url, headers=headers, stream=True, timeout=60,
                       proxies={"http": None, "https": None})
    resp.raise_for_status()

    # 诊断信息
    content_type = resp.headers.get("Content-Type", "").lower()
    total = int(resp.headers.get("Content-Length", 0))
    print(f"[诊断] HTTP {resp.status_code} | Content-Type: {content_type} "
          f"| Content-Length: {total} ({total/1024/1024:.1f} MB)")

    # 验证响应是视频内容，不是 HTML 错误页
    if "text/html" in content_type:
        preview = resp.text[:300]
        print(f"[诊断] HTML 错误页预览: {preview}")
        raise ValueError(
            f"CDN 返回了 HTML 页面而非视频，可能是 token 过期或被拦截。"
        )

    # 从 URL 或 Content-Disposition 推断扩展名
    ext = ".mp4"
    cd = resp.headers.get("Content-Disposition", "")
    cd_match = re.search(r'filename[^;=\n]*=["\']?(.*?)["\']?(?:;|$)', cd)
    if cd_match:
        cd_name = cd_match.group(1)
        ext = Path(cd_name).suffix or ext
    else:
        url_ext = Path(video_url.split("?")[0]).suffix
        if url_ext:
            ext = url_ext

    if not filename:
        filename = sanitize_filename(f"video_{int(time.time())}")

    filepath = Path(output_dir) / f"{filename}{ext}"
    # 避免覆盖
    counter = 1
    while filepath.exists():
        filepath = Path(output_dir) / f"{filename}_{counter}{ext}"
        counter += 1

    downloaded = 0
    start_time = time.time()
    with open(filepath, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:  # 过滤空 chunk（keep-alive）
                f.write(chunk)
                downloaded += len(chunk)
                elapsed = time.time() - start_time
                speed = downloaded / elapsed if elapsed > 0 else 0
                progress.update(downloaded, total, speed)

    progress.done()
    print(f"[诊断] 实际下载: {downloaded} bytes ({downloaded/1024/1024:.1f} MB)")

    # 验证下载结果
    actual_size = filepath.stat().st_size
    if actual_size == 0:
        filepath.unlink()
        raise ValueError("下载的文件大小为 0 bytes，CDN 返回了空内容。"
                         "请检查视频链接是否有效。")
    if actual_size < 10240:
        filepath.unlink()
        raise ValueError(f"下载的文件极小 ({actual_size} bytes)，"
                         "不是有效的视频文件，已删除。")
    if total > 0 and actual_size < total * 0.8:
        filepath.unlink()
        raise ValueError(
            f"下载不完整: 预期 {total} bytes，实际 {actual_size} bytes")

    return str(filepath)
