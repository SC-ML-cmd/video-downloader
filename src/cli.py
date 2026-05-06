"""命令行入口 — 通用网页视频下载器 CLI"""
import argparse
import sys
import json
import os
from pathlib import Path

# Windows 控制台 UTF-8 编码
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from colorama import init, Fore, Style

init(autoreset=True)

from .analyzer import analyze_video, list_formats
from .downloader import download_video, download_direct, DownloadProgress, DirectDownloadProgress
from .stream_parser import parse_m3u8, parse_mpd, detect_stream_type
from .utils import load_config, get_proxy, get_cookies_file, sanitize_filename


def cmd_analyze(args):
    """分析视频 URL"""
    config = load_config()
    proxy = args.proxy or get_proxy(config)
    cookies = args.cookies or get_cookies_file(config)

    print(f"{Fore.CYAN}正在分析: {args.url}{Style.RESET_ALL}")
    print()

    try:
        video_info = analyze_video(args.url, proxy=proxy,
                                   cookies_file=cookies)
        print(video_info.get_summary())

        if args.json:
            print(f"\n{Fore.YELLOW}JSON 输出:{Style.RESET_ALL}")
            json_data = {
                "title": video_info.title,
                "duration": video_info.duration,
                "uploader": video_info.uploader,
                "view_count": video_info.view_count,
                "formats": [
                    {"format_id": f.get("format_id"),
                     "ext": f.get("ext"),
                     "resolution": f.get("resolution"),
                     "filesize": f.get("filesize")}
                    for f in video_info.formats[:10]
                ]
            }
            print(json.dumps(json_data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"{Fore.RED}分析失败: {e}{Style.RESET_ALL}")
        sys.exit(1)


def cmd_formats(args):
    """列出视频可用格式"""
    config = load_config()
    proxy = args.proxy or get_proxy(config)
    cookies = args.cookies or get_cookies_file(config)

    print(f"{Fore.CYAN}获取格式列表: {args.url}{Style.RESET_ALL}")
    print()

    try:
        video_info = list_formats(args.url, proxy=proxy,
                                  cookies_file=cookies)
        print(f"标题: {video_info.title}")
        print(video_info.get_summary())

        # 显示推荐的下载命令
        print(f"\n{Fore.GREEN}推荐下载命令:{Style.RESET_ALL}")
        print(f"  python -m src.cli download \"{args.url}\"")
        if video_info.unique_formats:
            best_fmt = video_info.unique_formats[0]
            res = best_fmt.get("resolution", "")
            if res:
                h = int(res.split("x")[1]) if "x" in res else 0
                quality = f"{h}p" if h > 0 else "best"
                print(f"  python -m src.cli download \"{args.url}\" "
                      f"--quality {quality}")
    except Exception as e:
        print(f"{Fore.RED}获取格式失败: {e}{Style.RESET_ALL}")
        sys.exit(1)


def cmd_download(args):
    """下载视频 — yt-dlp 优先，自动降级到爬虫直链下载"""
    config = load_config()
    proxy = args.proxy or get_proxy(config)
    cookies = args.cookies or get_cookies_file(config)
    output_dir = args.output_dir or config.get("output_dir", "./downloads")

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    print(f"{Fore.CYAN}开始下载: {args.url}{Style.RESET_ALL}")
    print(f"输出目录: {output_dir}")
    if args.quality:
        print(f"画质: {args.quality}")
    print()

    # 第一步: 尝试 yt-dlp
    try:
        progress = DownloadProgress("下载")
        result = download_video(
            url=args.url,
            output_dir=output_dir,
            quality=args.quality,
            proxy=proxy,
            cookies_file=cookies,
            progress_hook=progress.progress_hook,
            playlist=args.playlist,
        )
        print(f"\n{Fore.GREEN}下载完成!{Style.RESET_ALL}")
        if result:
            rd = result.get("requested_downloads", [{}])
            if rd:
                filepath = rd[0].get("filepath", "未知路径")
                print(f"文件: {filepath}")
        return
    except Exception as e:
        error_msg = str(e)
        # 判断是否因为封禁/不支持而失败
        if any(kw in error_msg.lower() for kw in
               ["piracy", "no longer supported", "unsupported", "not supported",
                "unable to download webpage", "not available"]):
            print(f"{Fore.YELLOW}yt-dlp 不支持此网站，切换到爬虫模式...{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}yt-dlp 下载失败 ({(error_msg[:60])})，尝试爬虫模式...{Style.RESET_ALL}")

    # 第二步: 爬虫直链下载
    try:
        from .spiders.examples.generic_spider import GenericSpider
        spider = GenericSpider(proxy=proxy, cookies_file=cookies)
        filepath = spider.download_from_page(args.url, output_dir)

        print(f"\n{Fore.GREEN}下载完成!{Style.RESET_ALL}")
        print(f"文件: {filepath}")

        # 检查是否有音轨
        _check_audio(filepath)

    except Exception as e2:
        print(f"\n{Fore.RED}爬虫下载也失败: {e2}{Style.RESET_ALL}")
        sys.exit(1)


def _check_audio(filepath: str):
    """检查下载的视频是否有音轨"""
    import subprocess
    import json
    try:
        ffprobe_path = None
        from .utils import find_ffmpeg
        ffmpeg = find_ffmpeg()
        if ffmpeg:
            ffprobe_path = str(Path(ffmpeg).parent / "ffprobe.exe")

        if ffprobe_path:
            r = subprocess.run(
                [ffprobe_path, "-v", "quiet", "-print_format", "json",
                 "-show_streams", filepath],
                capture_output=True, text=True
            )
            streams = json.loads(r.stdout).get("streams", [])
            has_audio = any(s.get("codec_type") == "audio" for s in streams)
            if has_audio:
                print(f"{Fore.GREEN}[音频检测] 包含音频轨道{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}[音频检测] 警告: 未检测到音频轨道，可能为纯视频{Style.RESET_ALL}")
    except Exception:
        pass  # 音频检测失败不影响主流程


def cmd_stream(args):
    """分析流媒体 URL"""
    url = args.url
    stream_type = detect_stream_type(url)

    print(f"{Fore.CYAN}流媒体分析: {url}{Style.RESET_ALL}")
    print(f"检测类型: {stream_type.upper()}")
    print()

    try:
        if stream_type in ("hls", "unknown"):
            print(f"{Fore.YELLOW}尝试解析为 HLS/m3u8...{Style.RESET_ALL}")
            streams = parse_m3u8(url)
            if streams:
                _print_streams(streams, "HLS")
                return

        if stream_type in ("dash", "unknown"):
            print(f"{Fore.YELLOW}尝试解析为 DASH/mpd...{Style.RESET_ALL}")
            streams = parse_mpd(url)
            if streams:
                _print_streams(streams, "DASH")
                return

        if stream_type == "direct":
            print(f"{Fore.GREEN}直接视频链接，可直接下载{Style.RESET_ALL}")
            print(f"下载命令: python -m src.cli download \"{url}\"")

    except Exception as e:
        print(f"{Fore.RED}流媒体解析失败: {e}{Style.RESET_ALL}")
        sys.exit(1)


def cmd_spider(args):
    """使用爬虫分析网页中的视频资源"""
    from .spiders.examples.generic_spider import GenericSpider

    config = load_config()
    proxy = args.proxy or get_proxy(config)
    output_dir = args.output_dir or config.get("output_dir", "./downloads")

    print(f"{Fore.CYAN}爬虫分析: {args.url}{Style.RESET_ALL}")
    print()

    spider = GenericSpider(proxy=proxy)

    try:
        info = spider.extract_info(args.url)

        print(f"标题: {info['title']}")
        print(f"video 标签中的视频: {len(info['videos'])}")
        print(f"流媒体链接: {len(info['streams'])}")
        print(f"iframe 链接: {len(info['iframes'])}")
        print()

        if info["streams"]:
            print(f"{Fore.YELLOW}提取到的视频流:{Style.RESET_ALL}")
            print("-" * 60)
            for i, s in enumerate(info["streams"]):
                priority = s.get("priority", "normal")
                source = s.get("source", "regex")
                marker = f"{Fore.GREEN}[{priority}]{Style.RESET_ALL}" \
                         if priority == "high" else f"[{priority}]"
                print(f"  {i+1}. {marker} [{s['type']}] [{source}]")
                print(f"     {s['url'][:120]}")
            print()

        if args.download:
            best_url = spider.extract_best_video_url(args.url)
            if best_url:
                print(f"{Fore.CYAN}开始下载 (最佳视频链接)...{Style.RESET_ALL}")
                filename = sanitize_filename(info["title"])
                referer = "/".join(args.url.split("/")[:3]) + "/"
                progress = DirectDownloadProgress("下载")
                filepath = download_direct(
                    video_url=best_url,
                    output_dir=output_dir,
                    filename=filename,
                    referer=referer,
                    progress=progress,
                    session=spider.session,
                )
                print(f"\n{Fore.GREEN}下载完成: {filepath}{Style.RESET_ALL}")
                _check_audio(filepath)
            else:
                print(f"{Fore.RED}未提取到可下载的视频链接{Style.RESET_ALL}")

    except Exception as e:
        print(f"{Fore.RED}分析失败: {e}{Style.RESET_ALL}")
        sys.exit(1)


def _print_streams(streams, protocol: str):
    """打印流媒体列表"""
    print(f"\n{protocol} 流列表 ({len(streams)} 个):")
    print("-" * 70)
    videos = [s for s in streams if s.media_type == "video"]
    audios = [s for s in streams if s.media_type == "audio"]

    if videos:
        print(f"\n  视频流 ({len(videos)}):")
        for i, s in enumerate(sorted(videos, key=lambda x: x.bandwidth,
                                     reverse=True)):
            print(f"    {i+1:2d}. {s.resolution or '未知分辨率':>12s}  "
                  f"{s.bandwidth_mbps:6.1f}Mbps  "
                  f"fps={s.frame_rate:.0f}  "
                  f"codec={s.codecs[:30]}")

    if audios:
        print(f"\n  音频流 ({len(audios)}):")
        for i, s in enumerate(audios):
            print(f"    {i+1:2d}. {s.codecs or '默认':>10s}")


def main():
    parser = argparse.ArgumentParser(
        description="通用网页视频下载器 - 支持 B站、YouTube 等平台",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s analyze "https://www.bilibili.com/video/BV1xx411c7mD"
  %(prog)s formats "https://www.bilibili.com/video/BV1xx411c7mD"
  %(prog)s download "https://www.bilibili.com/video/BV1xx411c7mD" --quality 1080p
  %(prog)s stream "https://example.com/video.m3u8"
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # analyze 子命令
    analyze_p = subparsers.add_parser("analyze", help="分析视频信息（不下载）")
    analyze_p.add_argument("url", help="视频页面 URL")
    analyze_p.add_argument("--proxy", help="代理地址")
    analyze_p.add_argument("--cookies", help="cookies 文件路径")
    analyze_p.add_argument("--json", action="store_true",
                           help="同时输出 JSON 格式")

    # formats 子命令
    formats_p = subparsers.add_parser("formats", help="列出所有可用格式")
    formats_p.add_argument("url", help="视频页面 URL")
    formats_p.add_argument("--proxy", help="代理地址")
    formats_p.add_argument("--cookies", help="cookies 文件路径")

    # download 子命令
    download_p = subparsers.add_parser("download", help="下载视频")
    download_p.add_argument("url", help="视频页面 URL")
    download_p.add_argument("--output-dir", "-o", help="输出目录")
    download_p.add_argument("--quality", "-q",
                            choices=["2160p", "1440p", "1080p", "720p",
                                     "480p", "360p", "best", "worst"],
                            default=None,
                            help="画质选择 (默认: 最佳)")
    download_p.add_argument("--proxy", help="代理地址")
    download_p.add_argument("--cookies", help="cookies 文件路径")
    download_p.add_argument("--playlist", action="store_true",
                            help="下载整个播放列表")

    # stream 子命令
    stream_p = subparsers.add_parser("stream",
                                     help="分析流媒体 URL (m3u8/mpd)")
    stream_p.add_argument("url", help="流媒体 URL")
    stream_p.add_argument("--proxy", help="代理地址")

    # spider 子命令 — 网页视频链接提取
    spider_p = subparsers.add_parser("spider",
                                     help="用爬虫分析网页，提取视频链接")
    spider_p.add_argument("url", help="网页 URL")
    spider_p.add_argument("--download", "-d", action="store_true",
                          help="提取后直接下载")
    spider_p.add_argument("--output-dir", "-o", help="输出目录")
    spider_p.add_argument("--proxy", help="代理地址")

    args = parser.parse_args()

    if args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "formats":
        cmd_formats(args)
    elif args.command == "download":
        cmd_download(args)
    elif args.command == "stream":
        cmd_stream(args)
    elif args.command == "spider":
        cmd_spider(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
