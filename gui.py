"""通用网页视频下载器 GUI — 基于 tkinter 的简洁图形界面"""
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from pathlib import Path

# 将 src 加入路径
import sys
sys.path.insert(0, str(Path(__file__).parent))

from src.analyzer import analyze_video
from src.downloader import download_video, DownloadProgress
from src.utils import load_config


class VideoDownloaderGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("通用网页视频下载器 v1.0")
        self.root.geometry("800x600")
        self.root.minsize(600, 400)

        self.config = load_config()
        self.current_info = None

        self._build_ui()
        self._center_window()

    def _build_ui(self):
        # 主框架
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

        # 信息展示 + 进度 笔记本
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
                info = analyze_video(url)
                self.current_info = info
                self.root.after(0, lambda: self._show_info(info))
                self.root.after(0, lambda: self.status_var.set("分析完成"))
            except Exception as e:
                self.root.after(0, lambda: self._show_error(str(e)))
            finally:
                self.root.after(0, self.progress.stop)

        threading.Thread(target=_run, daemon=True).start()

    def _show_info(self, info):
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(1.0, info.get_summary())

    def _show_error(self, msg: str):
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(1.0, f"错误: {msg}")
        self.status_var.set("分析失败")
        self._log(msg, "ERROR")

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

        progress = DownloadProgress()

        def _run():
            try:
                result = download_video(
                    url=url,
                    output_dir=output_dir,
                    quality=quality,
                    progress_hook=progress.progress_hook,
                )
                filename = ""
                rd = result.get("requested_downloads", [{}])
                if rd:
                    filename = rd[0].get("filepath", "")
                msg = f"下载完成: {filename}" if filename else "下载完成"
                self.root.after(0, lambda: self._log(msg))
                self.root.after(0, lambda: self.status_var.set("下载完成"))
                self.root.after(0, lambda: messagebox.showinfo(
                    "完成", f"视频下载完成!\n{filename}"))
            except Exception as e:
                self.root.after(0, lambda: self._log(str(e), "ERROR"))
                self.root.after(0, lambda: self.status_var.set("下载失败"))
                self.root.after(0, lambda: messagebox.showerror(
                    "下载失败", str(e)))
            finally:
                self.root.after(0, self.progress.stop)

        threading.Thread(target=_run, daemon=True).start()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = VideoDownloaderGUI()
    app.run()
