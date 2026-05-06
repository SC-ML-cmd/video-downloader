"""通用工具函数"""
import os
import sys
import re
import json
import shutil
from pathlib import Path
from typing import Optional


def get_default_output_dir() -> Path:
    config = load_config()
    output_dir = config.get("output_dir", "./downloads")
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def sanitize_filename(filename: str) -> str:
    """清理文件名中的非法字符"""
    illegal_chars = r'[<>:"/\\|?*]'
    return re.sub(illegal_chars, "_", filename)


def format_size(size_bytes: Optional[int]) -> str:
    """格式化文件大小"""
    if size_bytes is None:
        return "未知"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def format_duration(seconds: Optional[int]) -> str:
    """格式化时长"""
    if seconds is None:
        return "未知"
    h, remainder = divmod(int(seconds), 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def find_ffmpeg() -> Optional[str]:
    """查找 ffmpeg 可执行文件路径"""
    # 1. 先检查 PATH
    path = shutil.which("ffmpeg")
    if path:
        return path

    # 2. Windows 常见安装位置
    if sys.platform == "win32":
        common_paths = [
            # winget 安装位置
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet",
            # scoop
            Path(os.environ.get("USERPROFILE", "")) / "scoop" / "shims",
            # chocolatey
            Path(os.environ.get("ProgramData", "")) / "chocolatey" / "bin",
            # 手动安装
            Path("C:/ffmpeg/bin"),
            Path(os.environ.get("ProgramFiles", "")) / "ffmpeg" / "bin",
        ]
        for base in common_paths:
            if base.exists():
                if base.name in ("WinGet",):
                    # 递归搜索 WinGet 目录下的 ffmpeg
                    for p in base.rglob("*/bin/ffmpeg.exe"):
                        return str(p)
                else:
                    exe = base / "ffmpeg.exe"
                    if exe.exists():
                        return str(exe)
    return None


def check_ffmpeg() -> bool:
    """检查 ffmpeg 是否可用"""
    return find_ffmpeg() is not None


def get_proxy(config: dict) -> Optional[str]:
    return config.get("proxy") or None


def get_cookies_file(config: dict) -> Optional[str]:
    cookies = config.get("cookies_file", "")
    return cookies if cookies and Path(cookies).exists() else None
