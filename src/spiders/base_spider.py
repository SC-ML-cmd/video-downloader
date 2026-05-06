"""基础爬虫抽象类"""
from abc import ABC, abstractmethod
from typing import Optional


class BaseSpider(ABC):
    """视频网站爬虫基类"""

    name: str = "base"
    domain: str = ""

    def __init__(self, proxy: Optional[str] = None,
                 cookies_file: Optional[str] = None):
        self.proxy = proxy
        self.cookies_file = cookies_file

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """判断是否能处理此 URL"""
        ...

    @abstractmethod
    def extract_info(self, url: str) -> dict:
        """提取视频信息，返回包含 title, url, formats 等字段的字典"""
        ...

    @abstractmethod
    def download(self, url: str, output_dir: str,
                 quality: Optional[str] = None) -> str:
        """下载视频，返回文件路径"""
        ...
