#!/usr/bin/env python3
"""
AstrBot v4 短视频解析插件 v0.3.16
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Tuple

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import Image, Node, Nodes, Plain, Video
from astrbot.api.star import Context, Star

# ---- 平台定义 ----

# 每个平台: (配置键名, 中文名称, 域名正则列表)
PLATFORM_CONFIGS: List[Tuple[str, str, List[str]]] = [
    ("douyin", "抖音", [r"v\.douyin\.com", r"www\.iesdouyin\.com", r"www\.douyin\.com"]),
    ("tiktok", "TikTok", [r"vm\.tiktok\.com", r"www\.tiktok\.com"]),
    ("kuaishou", "快手", [r"v\.kuaishou\.com"]),
    ("bilibili", "B站", [r"www\.bilibili\.com", r"bilibili\.com", r"b23\.tv"]),
    ("xiaohongshu", "小红书", [r"www\.xiaohongshu\.com", r"xhslink\.com", r"xhslink\.cn"]),
    ("weibo", "微博", [r"weibo\.com", r"weibo\.cn"]),
    ("xigua", "西瓜视频", [r"v\.ixigua\.com"]),
    ("weishi", "微视", [r"isee\.weishi\.qq\.com"]),
    ("pipixia", "皮皮虾", [r"h5\.pipix\.com"]),
    ("pipigx", "皮皮搞笑", [r"h5\.pipigx\.com", r"share\.xiaochuankeji\.cn"]),
    ("huoshan", "火山小视频", [r"share\.huoshan\.com"]),
    ("pear", "梨视频", [r"www\.pearvideo\.com"]),
    ("haokan", "好看视频", [r"xspshare\.baidu\.com", r"haokan\.baidu\.com", r"haokan\.hao123\.com"]),
    ("huya", "虎牙", [r"v\.huya\.com"]),
    ("acfun", "AcFun", [r"www\.acfun\.cn"]),
    ("meipai", "美拍", [r"meipai\.com"]),
    ("doupai", "逗拍", [r"doupai\.cc"]),
    ("quanminkge", "全民K歌", [r"kg\.qq\.com"]),
    ("sixroom", "6间房", [r"6\.cn"]),
    ("xinpianchang", "新片场", [r"xinpianchang\.com"]),
    ("twitter", "Twitter/X", [r"x\.com", r"twitter\.com", r"t\.co"]),
    ("zuiyou", "最右", [r"izuiyou\.com"]),
    ("cctv", "央视网", [r"tv\.cctv\.com", r"cctv\.com"]),
    ("sohu", "搜狐视频", [r"tv\.sohu\.com"]),
    ("tencent_video", "腾讯视频", [r"v\.qq\.com"]),
    ("lvzhou", "绿洲", [r"weibo\.cn"]),
    ("duxiao", "度小视", [r"quanmin\.baidu\.com"]),
]

# 构建综合正则（用于从消息中提取分享链接）
_ALL_DOMAIN_PATTERNS = "|".join(
    domain for _, _, domains in PLATFORM_CONFIGS for domain in domains
)
VIDEO_SHARE_URL_REGEX = re.compile(
    rf"(https?://)?({_ALL_DOMAIN_PATTERNS})(\S*)"
)

# 构建域名 → 平台键名的快速查找表
_DOMAIN_TO_PLATFORM: Dict[str, str] = {}
for _key, _name, _domains in PLATFORM_CONFIGS:
    for _domain in _domains:
        _DOMAIN_TO_PLATFORM[_domain] = _key

def get_platform_for_url(url: str) -> Optional[str]:
    """根据 URL 判断属于哪个平台，返回平台配置键名。"""
    for domain_pattern, platform_key in _DOMAIN_TO_PLATFORM.items():
        if re.search(domain_pattern, url):
            return platform_key
    return None

def is_platform_enabled(config: AstrBotConfig, platform_key: str) -> bool:
    """检查某个平台是否在配置中开启。"""
    config_key = f"platform_{platform_key}"
    return bool(config.get(config_key, True))

def get_platform_name(platform_key: str) -> str:
    """根据平台键名获取中文名称。"""
    for key, name, _ in PLATFORM_CONFIGS:
        if key == platform_key:
            return name
    return platform_key

# ---- 删除视频检测关键词 ----

VIDEO_DELETED_KEYWORDS = [
    "删除", "不存在", "已失效", "not found", "deleted",
    "已下架", "已过期", "无法查看", "已隐藏", "已屏蔽",
    "作品不见了", "内容不存在", "视频不见了", "找不到",
    "gone", "removed", "unavailable", "no longer",
]

def is_video_deleted_error(error_msg: str) -> bool:
    """判断解析错误是否为视频已删除。"""
    msg_lower = error_msg.lower()
    for keyword in VIDEO_DELETED_KEYWORDS:
        if keyword.lower() in msg_lower:
            return True
    return False

# ---- 默认配置 ----

DEFAULT_PARSER_API_BASE_URL = "http://192.168.5.116:8000"
DEFAULT_VIDEO_MAX_SIZE_MB = 50
DEFAULT_TIMEOUT_MS = 15000
DEFAULT_UNTITLED_TITLE = "未命名"
DEFAULT_UNKNOWN_AUTHOR = "未知作者"
DEFAULT_VIDEO_DELETED_MESSAGE = "该视频已被邪恶势力处理！！！"
DEFAULT_VIDEO_SENDING_MESSAGE = "视频解析成功，正在发送视频..."
DEFAULT_LOGIN_POLL_TIMEOUT = 300
DEFAULT_LOGIN_POLL_INTERVAL = 3
DEFAULT_ALBUM_MERGE_THRESHOLD = 9

# 抖音登录接口路径（相对 parser_api_base_url）
DOUYIN_LOGIN_QRCODE_PATH = "/douyin/login/qrcode"
DOUYIN_LOGIN_STATUS_PATH = "/douyin/login/status"
DOUYIN_LOGIN_CANCEL_PATH = "/douyin/login/cancel"

IMG_DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept": "image/webp,image/*,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

IMG_REFERER_HEADERS = {
    **IMG_DOWNLOAD_HEADERS,
    "Referer": "https://www.douyin.com/",
}

VIDEO_HEADERS = {
    "User-Agent": IMG_DOWNLOAD_HEADERS["User-Agent"],
    "Accept": "*/*",
    "Accept-Encoding": "identity",
}

VIDEO_REFERER_HEADERS = {
    **VIDEO_HEADERS,
    "Referer": "https://www.douyin.com/",
}

# 需要防盗链 Referer 的 CDN 域名（抖音系，与后端 web.py 映射保持一致）
ANTI_LEECH_DOMAINS = {
    "douyinpic.com", "douyinvod.com", "douyin.com",
    "iesdouyin.com", "douyinstatic.com", "amemv.com",
    "zjcdn.com", "pstatp.com", "byteimg.com", "bytecdn.cn",
    "snssdk.com", "muscdn.com", "ixigua.com",
}

# ---- 工具函数 ----

def request_json(url: str, *, timeout_ms: int) -> Tuple[Any, int]:
    try:
        with urllib.request.urlopen(url, timeout=timeout_ms / 1000.0) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status_code = int(getattr(resp, "status", 200))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {exc}") from exc
    return json.loads(body), status_code

def _needs_referer(url: str) -> bool:
    """判断 URL 是否需要防盗链 Referer 头。"""
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return False
    for domain in ANTI_LEECH_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return True
    return False

def download_image_bytes(url: str, timeout_ms: int) -> bytes:
    """下载图片，对抖音等 CDN 自动带 Referer 防 403。"""
    headers = IMG_REFERER_HEADERS if _needs_referer(url) else IMG_DOWNLOAD_HEADERS
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout_ms / 1000.0) as resp:
        return resp.read()

def image_url_to_base64(url: str, timeout_ms: int) -> str:
    """将图片 URL 下载并转为 base64 data URI。"""
    data = download_image_bytes(url, timeout_ms)
    content_type = "image/webp" if ".webp" in url.lower() else "image/jpeg"
    return f"data:{content_type};base64,{base64.b64encode(data).decode()}"

def regexp_match_url_from_string(text: str) -> Optional[str]:
    match = VIDEO_SHARE_URL_REGEX.search(text)
    if match is None:
        return None
    value = match.group(0)
    if "b23.tv" in value:
        value = value.replace(r"\/", "/").split("?", 1)[0]
    if not value.startswith("http"):
        return f"https://{value}"
    return value

def extract_url_from_event_text(event: AstrMessageEvent) -> Optional[str]:
    return regexp_match_url_from_string(event.get_message_str() or "")

def extract_url_from_json_segments(event: AstrMessageEvent) -> Optional[str]:
    candidates: List[str] = []
    msg_obj = getattr(event, "message_obj", None)
    if msg_obj is not None:
        try:
            candidates.append(json.dumps(msg_obj, default=str, ensure_ascii=False))
        except Exception:
            candidates.append(str(msg_obj))
    for attr in ("message_chain", "messages", "message"):
        chain = getattr(event, attr, None)
        if isinstance(chain, list):
            try:
                candidates.append(json.dumps(chain, default=str, ensure_ascii=False))
            except Exception:
                candidates.append(str(chain))
    if msg_obj is not None:
        for sub_attr in ("message", "messages", "message_chain", "data"):
            sub = getattr(msg_obj, sub_attr, None)
            if isinstance(sub, (list, dict)):
                try:
                    candidates.append(json.dumps(sub, default=str, ensure_ascii=False))
                except Exception:
                    candidates.append(str(sub))
    raw_msg = getattr(event, "raw_message", None) or getattr(event, "raw", None)
    if raw_msg:
        candidates.append(str(raw_msg))
    for text in candidates:
        url = regexp_match_url_from_string(text)
        if url:
            return url
    return None

def parse_remote_file_size_from_headers(headers: Mapping[str, str]) -> int | None:
    content_range = str(headers.get("Content-Range") or "").strip()
    if content_range:
        match = re.search(r"/(\d+)\s*$", content_range)
        if match:
            return int(match.group(1))
    content_length = str(headers.get("Content-Length") or "").strip()
    if content_length.isdigit():
        return int(content_length)
    return None

def build_remote_file_metadata_requests(file_url: str) -> List[urllib.request.Request]:
    """构造探测远程文件大小的 HEAD/GET 请求，抖音等防盗链 CDN 自动带 Referer。"""
    headers = VIDEO_REFERER_HEADERS if _needs_referer(file_url) else VIDEO_HEADERS
    return [
        urllib.request.Request(file_url, headers=headers, method="HEAD"),
        urllib.request.Request(
            file_url,
            headers={**headers, "Range": "bytes=0-0"},
            method="GET",
        ),
    ]


def download_video_to_file(url: str, dest_path: str, timeout_ms: int) -> int:
    """带防盗链 Referer 流式下载视频到本地文件，返回写入字节数。"""
    headers = VIDEO_REFERER_HEADERS if _needs_referer(url) else VIDEO_HEADERS
    req = urllib.request.Request(url, headers=headers)
    written = 0
    with urllib.request.urlopen(req, timeout=timeout_ms / 1000.0) as resp:
        with open(dest_path, "wb") as fh:
            while True:
                chunk = resp.read(512 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                written += len(chunk)
    return written


def _guess_video_suffix(url: str) -> str:
    """从 URL 推断视频文件扩展名，失败则回退 .mp4。"""
    path = urllib.parse.urlparse(url).path
    suffix = os.path.splitext(path)[1].lower()
    if suffix and len(suffix) <= 5 and suffix.isascii():
        return suffix
    return ".mp4"


def _get_video_temp_dir() -> str:
    """获取视频临时下载目录。必须位于 AstrBot data 挂载内，供 napcat 容器共享访问。"""
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

        base = get_astrbot_temp_path()
    except Exception:
        base = os.path.join(os.getcwd(), "data", "temp")
    temp_dir = os.path.join(base, "video_parser")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir


def _cleanup_stale_videos(temp_dir: str, max_age_seconds: int = 3600) -> None:
    """清理超过 max_age_seconds 的残留临时视频文件（防止崩溃后累积）。"""
    now = time.time()
    try:
        for name in os.listdir(temp_dir):
            path = os.path.join(temp_dir, name)
            try:
                if os.path.isfile(path) and now - os.path.getmtime(path) > max_age_seconds:
                    os.remove(path)
            except OSError:
                pass
    except OSError:
        pass


async def _delayed_remove(path: str, delay: float = 120.0) -> None:
    """延迟删除临时文件，给 napcat 留出上传时间。"""
    await asyncio.sleep(delay)
    try:
        os.remove(path)
    except OSError:
        pass

def ensure_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}

def ensure_list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [ensure_dict(item) for item in value]

def to_positive_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default

def to_non_negative_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number >= 0 else default

def empty_fallback(value: str, fallback: str) -> str:
    return value if value.strip() else fallback

def _pick_first_str(data: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = data.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return None

def _event_self_id(event: AstrMessageEvent) -> str:
    """获取机器人自身 id，兼容旧版本缺少 get_self_id 的情况。"""
    getter = getattr(event, "get_self_id", None)
    if callable(getter):
        try:
            value = getter()
        except Exception:
            value = ""
        return str(value or "").strip() or "0"
    return "0"

# ---- 插件主体 ----

class VideoParserPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.parser_api_base_url = (
            str(config.get("parser_api_base_url") or DEFAULT_PARSER_API_BASE_URL).strip()
            or DEFAULT_PARSER_API_BASE_URL
        )
        self.video_max_size_mb = to_positive_int(
            config.get("video_max_size_mb"), DEFAULT_VIDEO_MAX_SIZE_MB
        )
        self.request_timeout_ms = to_positive_int(
            config.get("request_timeout_ms"), DEFAULT_TIMEOUT_MS
        )
        self.send_cover = bool(config.get("send_cover", True))
        self.album_merge_threshold = to_non_negative_int(
            config.get("album_merge_threshold"), DEFAULT_ALBUM_MERGE_THRESHOLD
        )
        self.video_merge_message = bool(config.get("video_merge_message", False))
        self.send_processing_message = bool(config.get("send_processing_message", True))
        self.send_video_deleted_message = bool(config.get("send_video_deleted_message", True))
        self.send_video_sending_message = bool(config.get("send_video_sending_message", True))
        self.processing_message = str(
            config.get("processing_message") or "ikun解析bot正在处理中。。。"
        ).strip()
        self.video_deleted_message = str(
            config.get("video_deleted_message") or DEFAULT_VIDEO_DELETED_MESSAGE
        ).strip()
        self.video_sending_message = str(
            config.get("video_sending_message") or DEFAULT_VIDEO_SENDING_MESSAGE
        ).strip() or DEFAULT_VIDEO_SENDING_MESSAGE
        self.douyin_login_poll_timeout = to_positive_int(
            config.get("douyin_login_poll_timeout"), DEFAULT_LOGIN_POLL_TIMEOUT
        )
        self.douyin_login_poll_interval = to_positive_int(
            config.get("douyin_login_poll_interval"), DEFAULT_LOGIN_POLL_INTERVAL
        )
        self._active_login_event: Optional[AstrMessageEvent] = None

        # 打印已启用的平台
        enabled_platforms = [
            name for key, name, _ in PLATFORM_CONFIGS
            if is_platform_enabled(self.config, key)
        ]
        logger.info(
            f"video_parser v0.3.16 initialized: "
            f"api={self.parser_api_base_url} "
            f"max_size={self.video_max_size_mb}MB "
            f"login_poll_timeout={self.douyin_login_poll_timeout}s "
            f"enabled_platforms({len(enabled_platforms)}): {', '.join(enabled_platforms)}"
        )

    # ---- 消息事件处理器 ----

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        share_url = extract_url_from_event_text(event)
        if share_url is None:
            share_url = extract_url_from_json_segments(event)
            if share_url is not None:
                logger.info(f"video_parser URL from JSON: {share_url}")
        if share_url is None:
            return

        # 平台开关检查
        platform_key = get_platform_for_url(share_url)
        if platform_key is None:
            logger.info(f"video_parser unrecognized platform for url: {share_url}")
            return
        if not is_platform_enabled(self.config, platform_key):
            platform_name = get_platform_name(platform_key)
            logger.info(
                f"video_parser platform '{platform_name}' is disabled, skipping: {share_url}"
            )
            return

        if self.send_processing_message:
            yield event.plain_result(self.processing_message)

        try:
            video_data = await self.parse_video_share_url(share_url)

            if ensure_list(video_data.get("images")):
                async for result in self._handle_album(event, video_data):
                    yield result
                return
            if str(video_data.get("video_url") or "").strip():
                async for result in self._handle_video(event, video_data):
                    yield result
                return

            yield event.plain_result("解析成功，但链接内容好像既不是视频也不是图集呢")

        except VideoDeletedError:
            logger.info(f"video_parser video deleted: {share_url}")
            if self.send_video_deleted_message:
                yield event.plain_result(self.video_deleted_message)
        except Exception as exc:
            logger.error(f"video_parser error url={share_url}: {exc}\n{traceback.format_exc()}")
            yield event.plain_result(f"解析失败：{exc}")

    # ---- 抖音扫码登录 ----

    @filter.command("dy登陆", alias={"dy登录", "dy扫码", "扫码登录", "抖音登录"})
    async def dy_login(self, event: AstrMessageEvent):
        """发起抖音网页版扫码登录，返回二维码并后台自动检测登录状态。"""
        if self._active_login_event is not None:
            yield event.plain_result("已有一个登录会话在进行中，请先完成或等待其超时")
            return

        qrcode_url = self.parser_api_base_url + DOUYIN_LOGIN_QRCODE_PATH
        loop = asyncio.get_running_loop()
        try:
            payload, status_code = await loop.run_in_executor(
                None, lambda: request_json(qrcode_url, timeout_ms=self.request_timeout_ms)
            )
        except Exception as exc:
            logger.error(f"video_parser douyin login qrcode request failed: {exc}")
            yield event.plain_result(f"获取登录二维码失败：{exc}")
            return

        result = ensure_dict(payload)
        code = to_positive_int(result.get("code"), -1)
        if code != 200 or status_code != 200:
            msg = str(result.get("msg") or "").strip() or f"HTTP {status_code}"
            yield event.plain_result(f"获取登录二维码失败：{msg}")
            return

        data = ensure_dict(result.get("data"))
        qr_base64 = str(data.get("qrcode_base64") or "").strip()
        expires_in = to_positive_int(data.get("expires_in"), self.douyin_login_poll_timeout)

        if not qr_base64:
            yield event.plain_result("获取登录二维码失败：返回内容为空")
            return

        self._active_login_event = event
        # 先启动后台轮询任务，再发送二维码（避免框架提前停止迭代导致轮询未启动）
        asyncio.create_task(self._poll_douyin_login(event))
        try:
            yield event.chain_result([
                Image.fromBase64(qr_base64),
                Plain(
                    f"\n请用抖音 APP 扫码登录（{expires_in} 秒内有效）\n"
                    f"扫码成功后我会自动检测并通知你"
                ),
            ])
        except Exception as exc:
            logger.warning(f"video_parser send qrcode image failed: {exc}")
            self._active_login_event = None
            yield event.plain_result(f"二维码已生成，但发送图片失败：{exc}")
            return

    async def _poll_douyin_login(self, event: AstrMessageEvent):
        """后台轮询抖音登录状态，成功后主动推送结果。"""
        deadline = time.monotonic() + self.douyin_login_poll_timeout
        status_url = self.parser_api_base_url + DOUYIN_LOGIN_STATUS_PATH
        loop = asyncio.get_running_loop()
        last_state = ""

        try:
            while time.monotonic() < deadline:
                await asyncio.sleep(self.douyin_login_poll_interval)
                try:
                    payload, _status_code = await loop.run_in_executor(
                        None, lambda: request_json(status_url, timeout_ms=self.request_timeout_ms)
                    )
                except Exception as exc:
                    logger.warning(f"video_parser douyin login status poll failed: {exc}")
                    continue

                data = ensure_dict(ensure_dict(payload).get("data"))
                state = str(data.get("status") or "")
                if state and state != last_state:
                    logger.info(f"video_parser douyin login state: {state}")
                    last_state = state

                if state == "success":
                    await self._safe_send(
                        event,
                        "✅ 抖音登录成功！Cookie 已保存，现在可以正常解析抖音视频/图集了",
                    )
                    return
                if state in ("expired", "cancelled", "failed"):
                    if state == "expired":
                        await self._safe_send(event, "⏰ 登录二维码已过期，请重新发送 /dy登陆")
                    elif state == "cancelled":
                        await self._safe_send(event, "登录已取消")
                    else:
                        err = str(data.get("error") or "").strip()
                        await self._safe_send(event, f"❌ 抖音登录失败：{err or state}")
                    return

            await self._safe_send(event, "⏰ 登录超时，请重新发送 /dy登陆")
        finally:
            if self._active_login_event is event:
                self._active_login_event = None

    async def _safe_send(self, event: AstrMessageEvent, text: str):
        """主动推送一条文本消息，失败时仅记录日志不抛出。"""
        try:
            await event.send(MessageChain([Plain(text)]))
        except Exception as exc:
            logger.error(f"video_parser douyin login push failed: {exc}")

    # ---- 图集处理 ----

    async def _handle_album(self, event: AstrMessageEvent, data: Dict[str, Any]):
        images = ensure_list(data.get("images"))
        title = str(data.get("title") or "").strip()
        author = str(ensure_dict(data.get("author")).get("name") or "").strip()
        total = len(images)

        summary = f"图集解析成功！共 {total} 张图片"
        if title:
            summary += f"\n标题: {empty_fallback(title, DEFAULT_UNTITLED_TITLE)}"
        if author:
            summary += f"\n作者: {empty_fallback(author, DEFAULT_UNKNOWN_AUTHOR)}"

        logger.info(f"video_parser album: {total} images, title={title[:30] if title else 'N/A'}")
        yield event.plain_result(summary)

        loop = asyncio.get_running_loop()
        merge = self.album_merge_threshold > 0 and total > self.album_merge_threshold

        if merge:
            logger.info(
                f"video_parser album merged into one message: {total} images > "
                f"threshold {self.album_merge_threshold}"
            )
            chain: List[Any] = []
            sent = 0
            for index, image in enumerate(images, start=1):
                image_url = str(image.get("url") or "").strip()
                if not image_url:
                    logger.warning(f"video_parser image {index} has no url, skipping")
                    continue

                try:
                    b64 = await loop.run_in_executor(
                        None, lambda u=image_url: image_url_to_base64(u, self.request_timeout_ms)
                    )
                    chain.append(Image(file=b64))
                    sent += 1
                except Exception as exc:
                    logger.warning(f"video_parser image {index} download/send failed: {exc}")
                    try:
                        chain.append(Image.fromURL(image_url))
                        sent += 1
                    except Exception as exc2:
                        logger.warning(f"video_parser image {index} url fallback also failed: {exc2}")
                        chain.append(Plain(f"第 {index} 张图片发送失败"))
                if total > 1:
                    chain.append(Plain(f"第 {index}/{total} 张"))

            if chain:
                yield event.chain_result(chain)
            if sent == 0:
                yield event.plain_result("图集解析成功，但所有图片发送失败")
            return

        sent = 0
        for index, image in enumerate(images, start=1):
            image_url = str(image.get("url") or "").strip()
            if not image_url:
                logger.warning(f"video_parser image {index} has no url, skipping")
                continue

            try:
                b64 = await loop.run_in_executor(
                    None, lambda u=image_url: image_url_to_base64(u, self.request_timeout_ms)
                )
                yield event.chain_result([Image(file=b64)])
                sent += 1
            except Exception as exc:
                logger.warning(f"video_parser image {index} download/send failed: {exc}")
                try:
                    yield event.chain_result([Image.fromURL(image_url)])
                    sent += 1
                except Exception as exc2:
                    logger.warning(f"video_parser image {index} url fallback also failed: {exc2}")
                    yield event.plain_result(f"第 {index} 张图片发送失败")

        if sent == 0:
            yield event.plain_result("图集解析成功，但所有图片发送失败")

    # ---- 视频处理 ----

    async def _cover_segment(self, cover_url: str) -> Optional[Any]:
        """下载封面并返回 Image 段（base64 优先，兜底 URL），失败返回 None。"""
        loop = asyncio.get_running_loop()
        try:
            b64 = await loop.run_in_executor(
                None, lambda u=cover_url: image_url_to_base64(u, self.request_timeout_ms)
            )
            return Image(file=b64)
        except Exception as exc:
            logger.warning(f"video_parser cover failed: {exc}")
            try:
                return Image.fromURL(cover_url)
            except Exception:
                return None

    async def _handle_video(self, event: AstrMessageEvent, data: Dict[str, Any]):
        if self.send_video_sending_message:
            yield event.plain_result(self.video_sending_message)

        video_url = str(data.get("video_url") or "").strip()

        cover_segment: Optional[Any] = None
        if self.send_cover:
            cover_url = _pick_first_str(data, "cover_url", "cover", "thumbnail", "thumb", "poster")
            if cover_url:
                segment = await self._cover_segment(cover_url)
                if self.video_merge_message:
                    cover_segment = segment
                elif segment is not None:
                    yield event.chain_result([segment])

        try:
            file_size = await self._get_remote_file_size(video_url)
        except Exception as exc:
            logger.warning(f"video_parser probe size failed: {exc}")
            yield event.plain_result("获取视频大小失败，无法直接发送，请尝试点击源链接观看。")
            return

        threshold = self.video_max_size_mb * 1024 * 1024
        if file_size > threshold:
            yield event.plain_result(
                f"视频大小为 {file_size / (1024 * 1024):.2f}MB，"
                f"超过 {self.video_max_size_mb}MB 限制，请尝试点击源链接观看。"
            )
            return

        # 带 Referer 下载视频到本地临时文件，避免 napcat 直连抖音 CDN 触发 403 防盗链
        loop = asyncio.get_running_loop()
        temp_dir = _get_video_temp_dir()
        _cleanup_stale_videos(temp_dir)
        tmp_path = os.path.join(
            temp_dir, f"vp_{int(time.time())}_{os.getpid()}{_guess_video_suffix(video_url)}"
        )
        try:
            downloaded = await loop.run_in_executor(
                None,
                lambda: download_video_to_file(
                    video_url, tmp_path, self.request_timeout_ms
                ),
            )
            if downloaded <= 0:
                raise RuntimeError("下载到 0 字节")
        except Exception as exc:
            logger.warning(f"video_parser video download failed: {exc}")
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            yield event.plain_result("视频下载失败，无法直接发送，请尝试点击源链接观看。")
            return

        title = str(data.get("title") or "").strip()
        author = str(ensure_dict(data.get("author")).get("name") or "").strip()
        title_author_text = ""
        if title or author:
            title_author_text = (
                f"标题: {empty_fallback(title, DEFAULT_UNTITLED_TITLE)}\n"
                f"作者: {empty_fallback(author, DEFAULT_UNKNOWN_AUTHOR)}"
            )

        video_segment = Video.fromFileSystem(tmp_path)

        if self.video_merge_message:
            # 使用合并转发：信息（封面图+标题作者）与视频各占一个节点。
            # QQ 展开单个节点只会渲染一种主媒体，混合塞进一个节点会导致图文丢失。
            uin = _event_self_id(event)
            nodes: List[Any] = []

            info_content: List[Any] = []
            if cover_segment is not None:
                info_content.append(cover_segment)
            if title_author_text:
                info_content.append(Plain(title_author_text))
            if info_content:
                nodes.append(Node(uin=uin, name="视频解析", content=info_content))

            nodes.append(Node(uin=uin, name="视频解析", content=[video_segment]))

            yield event.chain_result([Nodes(nodes)])
        else:
            # 关闭合并转发：标题作者与视频分开发送，
            # 避免文字与视频混在同一消息链中被视频覆盖丢失
            if title_author_text:
                yield event.plain_result(title_author_text)
            yield event.chain_result([video_segment])

        # 延迟清理临时文件，给 napcat 留出上传时间
        asyncio.create_task(_delayed_remove(tmp_path))

    # ---- 核心解析逻辑 ----

    async def parse_video_share_url(self, share_url: str) -> Dict[str, Any]:
        base_url = self.parser_api_base_url.rstrip("/")
        full_url = (
            f"{base_url}/video/share/url/parse"
            f"?url={urllib.parse.quote(share_url, safe='')}"
        )
        loop = asyncio.get_running_loop()
        payload, _status = await loop.run_in_executor(
            None, lambda: request_json(full_url, timeout_ms=self.request_timeout_ms)
        )
        result = ensure_dict(payload)
        code = int(result.get("code") or 0)
        if code != 200:
            error_msg = str(result.get("msg") or "")
            if is_video_deleted_error(error_msg):
                raise VideoDeletedError(
                    f"video deleted: {error_msg} (code={code})"
                )
            raise RuntimeError(f"parser error: {error_msg} ({code})")
        return ensure_dict(result.get("data"))

    async def _get_remote_file_size(self, file_url: str) -> int:
        loop = asyncio.get_running_loop()
        timeout_seconds = self.request_timeout_ms / 1000.0
        errors: List[str] = []

        for request in build_remote_file_metadata_requests(file_url):
            method = request.get_method()
            try:
                response = await loop.run_in_executor(
                    None,
                    lambda r=request: urllib.request.urlopen(r, timeout=timeout_seconds),
                )
                status_code = int(getattr(response, "status", 200))
                if not 200 <= status_code < 300:
                    raise RuntimeError(f"{method} failed: {status_code}")
                file_size = parse_remote_file_size_from_headers(response.headers)
                if file_size is not None:
                    return file_size
                raise RuntimeError(f"{method} missing size headers")
            except urllib.error.HTTPError as exc:
                errors.append(f"{method} HTTP {exc.code}")
            except urllib.error.URLError as exc:
                errors.append(f"{method} {exc.reason or exc}")
            except RuntimeError as exc:
                errors.append(str(exc))

        raise RuntimeError("; ".join(errors) or "failed to probe remote file size")

# ---- 自定义异常 ----

class VideoDeletedError(RuntimeError):
    """视频已被删除的异常。"""
    pass