# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

通用网页视频下载器，双引擎架构：**yt-dlp 主引擎 + 爬虫直链引擎**。
- yt-dlp 支持 B站、YouTube 等数千平台
- 爬虫引擎处理 yt-dlp 已封禁或不支持的网站（HTML 解析 + 反混淆 + HTTP 直链下载）

## 常用命令

```bash
# ===== CLI =====
python -m src.cli analyze "<video_url>"           # 分析视频元数据（yt-dlp 提取）
python -m src.cli formats "<video_url>"           # 列出可用格式
python -m src.cli download "<video_url>" -q 1080p # 下载（自动降级：yt-dlp → 爬虫）
python -m src.cli stream "<m3u8_or_mpd_url>"     # 解析 HLS/DASH 流媒体
python -m src.cli spider "<page_url>"             # 爬虫分析网页视频
python -m src.cli spider "<page_url>" --download  # 爬虫分析 + 直链下载

# ===== GUI =====
python gui.py

# ===== 测试 =====
python tests/test_analyzer.py

# ===== 依赖 =====
pip install -r requirements.txt
```

## 核心架构

### 双引擎下载流程

```
用户 URL → cmd_download()
  ├── 主引擎: yt-dlp → 成功 → 完成
  └── 降级引擎: 爬虫提取视频 URL → HTTP 直链下载
```

### 模块说明

- **[src/analyzer.py](src/analyzer.py)** — `analyze_video()` 调用 yt-dlp 提取视频元数据，返回 `VideoInfo` 对象
- **[src/downloader.py](src/downloader.py)** — 双模式下载：
  - `download_video()` — 基于 yt-dlp，支持格式选择、音视频合并
  - `download_direct()` — HTTP 直链下载（自动 Referer、Content-Disposition 检测、进度显示）
  - `DirectDownloadProgress` — 直链下载进度回调
- **[src/stream_parser.py](src/stream_parser.py)** — 不依赖 yt-dlp，用 `requests` + `m3u8` 解析 HLS/DASH 播放列表，返回 `StreamInfo` 列表
- **[src/utils.py](src/utils.py)** — 配置加载、智能 ffmpeg 查找（PATH → winget/scoop/choco 常见路径）、格式化工具
- **[src/spiders/](src/spiders/)** — 爬虫框架：
  - `BaseSpider` — 抽象基类 (`can_handle` / `extract_info` / `download`)
  - `BilibiliSpider` — B站适配示例
  - `GenericSpider` — **通用爬虫核心**，包含：
    - `extract_best_video_url()` — URL 提取优先级：strencode2 解码 > HTML 注释备用 > 正则匹配
    - `_decode_strencode()` — 支持 strencode2 (unescape) 和 strencode (XOR+base64) 两种反混淆
    - `download_from_page()` — 完整流程：提取 URL → 获取标题 → HTTP 直链下载 + Referer

## 配置

复制 `config.json.example` 为 `config.json`：
- `output_dir`: 下载目录（默认 `./downloads`）
- `proxy`: 代理地址
- `cookies_file`: Netscape 格式 cookies（B站高画质需要）
- `headers`: 自定义 HTTP 请求头

## 项目特点

- **双引擎降级**：yt-dlp 被封禁时自动切换到爬虫 HTTP 直链，无需用户干预
- **反混淆支持**：处理 strencode/strencode2 等 JS 混淆编码
- **中文化质参数**：2160p/1080p/720p 等，自建 format selector 映射
- **ffmpeg 自适应**：自动检测 ffmpeg 位置，不可用时降级为单文件格式
- **下载后音轨检测**：自动调用 ffprobe 验证下载文件是否包含音频轨道
- **Windows 适配**：控制台 UTF-8 编码 + colorama 彩色输出

# 重要
请用中文进行所有思考、推理和回答，包括内部思考链。
