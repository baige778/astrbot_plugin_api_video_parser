"""API 视频/图集解析插件。

导出 VideoParserPlugin，AstrBot 通过本模块加载插件。
"""

from .main import VideoParserPlugin

__all__ = ["VideoParserPlugin"]
