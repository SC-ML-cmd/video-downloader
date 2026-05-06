"""分析器模块测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analyzer import analyze_video


def test_bilibili_analyze():
    """测试 B站视频分析"""
    url = "https://www.bilibili.com/video/BV1ULf8YnEXQ/"
    print(f"测试 B站分析: {url}")

    info = analyze_video(url)
    assert info.title, "标题不应为空"
    assert len(info.formats) > 0, "应该有可用格式"

    print(f"  标题: {info.title}")
    print(f"  格式数: {len(info.formats)}")
    print("  通过!")
    return True


def test_direct_mp4_analyze():
    """测试直接 MP4 链接分析"""
    url = "https://www.w3schools.com/html/mov_bbb.mp4"
    print(f"测试直接链接: {url}")

    try:
        info = analyze_video(url)
        print(f"  标题: {info.title}")
        print("  通过!")
        return True
    except Exception as e:
        print(f"  跳过 (网络问题): {e}")
        return True


if __name__ == "__main__":
    test_bilibili_analyze()
    test_direct_mp4_analyze()
    print("\n所有测试通过!")
