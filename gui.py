"""通用网页视频下载器 GUI — 基于 tkinter 的简洁图形界面"""
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))

from src.analyzer import analyze_video
from src.downloader import download_video, download_direct, DownloadProgress
from src.utils import load_config


class VideoDownloaderGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("通用网页视频下载器 v1.0")
        self.root.geometry("800x600")
        self.root.minsize(600, 400)

        self.config = load_config()
        self.current_info = None
        self.current_video_url = None  # 爬虫提取到的直链 URL

        self._build_ui()
        self._center_window()

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # URL 输入区
        url_frame = ttk.LabelFrame(main_frame, text="视频 URL", padding="5")
        url_frame.pack(fill=tk.X, pady=(0, 10))

        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(url_frame, textvariable=self.url_var)
        url_entry.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 5))

        ttk.Button(url_frame, text="分析",
                   command=self._do_analyze).pack(side=tk.LEFT, padx=2)
        ttk.Button(url_frame, text="下载",
                   command=self._do_download).pack(side=tk.LEFT, padx=2)

        # 下载模式提示
        ttk.Label(main_frame, text="支持 yt-dlp 引擎 + 爬虫直链下载，yt-dlp 失败时自动切换",
                  foreground="gray").pack(anchor=tk.W, pady=(0, 5))

        # 控制面板
        ctrl_frame = ttk.Frame(main_frame)
        ctrl_frame.pack(fill=tk.X, pady=(0, 10))

        # 输出目录
        ttk.Label(ctrl_frame, text="输出目录:").pack(side=tk.LEFT)
        self.output_dir_var = tk.StringVar(
            value=self.config.get("output_dir", "./downloads"))
        ttk.Entry(ctrl_frame, textvariable=self.output_dir_var,
                  width=30).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_frame, text="浏览",
                   command=self._browse_dir).pack(side=tk.LEFT)

        # 画质选择
        ttk.Label(ctrl_frame, text="画质:").pack(side=tk.LEFT, padx=(10, 0))
        self.quality_var = tk.StringVar(value="best")
        quality_combo = ttk.Combobox(ctrl_frame, textvariable=self.quality_var,
                                     values=["best", "2160p", "1440p",
                                             "1080p", "720p", "480p", "360p"],
                                     width=8, state="readonly")
        quality_combo.pack(side=tk.LEFT, padx=5)

        # 笔记本
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # 信息页面
        info_frame = ttk.Frame(notebook)
        notebook.add(info_frame, text="视频信息")
        self.info_text = scrolledtext.ScrolledText(
            info_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.info_text.pack(fill=tk.BOTH, expand=True)

        # 日志页面
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="下载日志")
        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 进度条
        self.progress = ttk.Progressbar(main_frame, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(5, 0))

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var,
                               relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, pady=(5, 0))

    def _center_window(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"+{x}+{y}")

    def _browse_dir(self):
        dir_path = filedialog.askdirectory(title="选择下载目录")
        if dir_path:
            self.output_dir_var.set(dir_path)

    def _log(self, msg: str, tag: str = "INFO"):
        self.log_text.insert(tk.END, f"[{tag}] {msg}\n")
        self.log_text.see(tk.END)

    # ===== 分析 =====

    def _do_analyze(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请输入视频 URL")
            return

        self.status_var.set("正在分析...")
        self.info_text.delete(1.0, tk.END)
        self.progress["mode"] = "indeterminate"
        self.progress.start()

        def _run():
            try:
                # 先尝试 yt-dlp
                info = analyze_video(url)
                self.current_info = info
                self.current_video_url = None
                summary = info.get_summary()
                self.root.after(0, lambda s=summary: self._show_info(s))
                self.root.after(0, lambda: self._log("yt-dlp 分析成功", "OK"))
                self.root.after(0, lambda: self.status_var.set("分析完成 (yt-dlp)"))
            except Exception as e:
                ytdlp_err = str(e)[:80]
                self.root.after(0, lambda msg=ytdlp_err: self._log(
                    f"yt-dlp 分析失败: {msg}，切换到爬虫...", "WARN"))
                # 降级到爬虫
                try:
                    from src.spiders.examples.generic_spider import GenericSpider
                    spider = GenericSpider()
                    spider_info = spider.extract_info(url)
                    self.current_video_url = spider.extract_best_video_url(url)

                    lines = [
                        "=" * 50,
                        f"  标题: {spider_info['title']}",
                        f"  来源: 爬虫引擎 (yt-dlp 不支持此网站)",
                        "=" * 50,
                        f"  流媒体链接: {len(spider_info['streams'])} 个",
                    ]
                    for i, s in enumerate(spider_info["streams"]):
                        priority = s.get("priority", "normal")
                        tag = "[优先]" if priority == "high" else "[备用]"
                        lines.append(f"  {i+1}. {tag} {s['url'][:100]}...")

                    summary = "\n".join(lines)
                    stream_count = len(spider_info["streams"])
                    self.root.after(0, lambda s=summary: self._show_info(s))
                    self.root.after(0, lambda c=stream_count: self._log(
                        f"爬虫发现 {c} 个视频流", "OK"))
                    self.root.after(0, lambda: self.status_var.set("分析完成 (爬虫)"))
                except Exception as e2:
                    err_detail = f"分析失败:\nyt-dlp: {ytdlp_err}\n爬虫: {str(e2)[:100]}"
                    self.root.after(0, lambda msg=err_detail: self._show_error(msg))
            finally:
                self.root.after(0, self.progress.stop)

        threading.Thread(target=_run, daemon=True).start()

    def _show_info(self, text: str):
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(1.0, text)

    def _show_error(self, msg: str):
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(1.0, f"错误:\n{msg}")
        self.status_var.set("分析失败")
        self._log(msg, "ERROR")

    # ===== 下载 =====

    def _do_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请输入视频 URL")
            return

        output_dir = self.output_dir_var.get().strip() or "./downloads"
        quality = self.quality_var.get()

        self.status_var.set("正在下载...")
        self.progress["mode"] = "indeterminate"
        self.progress.start()

        def _run():
            # 方案 A: yt-dlp
            try:
                self.root.after(0, lambda: self._log("尝试 yt-dlp 下载..."))
                result = download_video(
                    url=url, output_dir=output_dir, quality=quality,
                    progress_hook=DownloadProgress().progress_hook,
                )
                filepath = ""
                rd = result.get("requested_downloads", [{}])
                if rd:
                    filepath = rd[0].get("filepath", "")
                self.root.after(0, lambda fp=filepath: self._on_done(fp))
                return
            except Exception as e:
                ytdlp_err = str(e)[:80]
                self.root.after(0, lambda msg=ytdlp_err: self._log(
                    f"yt-dlp 失败: {msg}，切换到爬虫引擎...", "WARN"))

            # 方案 B: 爬虫 + HTTP 直链
            try:
                from src.spiders.examples.generic_spider import GenericSpider
                from src.utils import sanitize_filename
                from urllib.parse import urlparse
                from bs4 import BeautifulSoup
                import re

                spider = GenericSpider()

                # 一次性获取页面，同时提取 URL 和标题
                self.root.after(0, lambda: self._log("爬虫正在解析网页...", "INFO"))
                resp = spider.session.get(url, timeout=30,
                                          proxies={"http": None, "https": None})
                resp.raise_for_status()
                html = resp.text

                video_url = spider._decode_strencode(html)
                if not video_url:
                    video_url = spider.extract_best_video_url(url)

                # 直接从已获取的 HTML 中提取标题（避免二次请求）
                soup = BeautifulSoup(html, "html.parser")
                title = spider._extract_title(soup)

                if not video_url:
                    raise ValueError("爬虫未能提取到视频链接")

                self.root.after(0, lambda u=video_url[:120]: self._log(
                    f"爬虫发现视频: {u}...", "INFO"))
                self.root.after(0, lambda t=title: self._log(
                    f"标题: {t}", "INFO"))

                # 构建 Referer
                parsed = urlparse(url)
                referer = f"{parsed.scheme}://{parsed.netloc}/"
                safe_name = sanitize_filename(title)

                # 用 spider 的 session 下载（复用连接、绕过代理）
                self.root.after(0, lambda: self._log("开始 HTTP 直链下载...", "INFO"))
                filepath = download_direct(
                    video_url=video_url,
                    output_dir=output_dir,
                    filename=safe_name,
                    referer=referer,
                    session=spider.session,
                )

                # 音轨检测
                audio_ok = self._check_audio(filepath)
                self.root.after(0, lambda fp=filepath, ao=audio_ok: self._on_done(fp, ao))
            except Exception as e2:
                err_detail = f"yt-dlp 和爬虫均失败:\n{str(e2)[:300]}"
                self.root.after(0, lambda msg=err_detail: self._log(msg, "ERROR"))
                self.root.after(0, lambda: self.status_var.set("下载失败"))
                self.root.after(0, lambda msg=err_detail: messagebox.showerror("下载失败", msg))
            finally:
                self.root.after(0, self.progress.stop)

        threading.Thread(target=_run, daemon=True).start()

    def _on_done(self, filepath: str, has_audio: bool = True):
        short = Path(filepath).name if filepath else "未知"
        self._log(f"下载完成: {short}")
        audio_tag = " 有音轨" if has_audio else " 无声!"
        self.status_var.set(f"下载完成{audio_tag}")
        self.progress.stop()
        messagebox.showinfo("完成", f"视频下载完成!\n{filepath}")

    def _check_audio(self, filepath: str) -> bool:
        """检查是否有音频轨道"""
        import subprocess
        import json
        from src.utils import find_ffmpeg
        try:
            ffmpeg = find_ffmpeg()
            if ffmpeg:
                ffprobe = str(Path(ffmpeg).parent / "ffprobe.exe")
                r = subprocess.run(
                    [ffprobe, "-v", "quiet", "-print_format", "json",
                     "-show_streams", filepath],
                    capture_output=True, text=True
                )
                streams = json.loads(r.stdout).get("streams", [])
                return any(s.get("codec_type") == "audio" for s in streams)
        except Exception:
            pass
        return True  # 检测失败时不报错

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = VideoDownloaderGUI()
    app.run()
