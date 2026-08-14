#!/usr/bin/env python3
"""
AstrBot v4 短视频解析插件 v0.2.4
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import traceback
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Tuple

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Plain, Video
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

# ---- 后端临时错误检测（可重试的错误） ----

BACKEND_TEMPORARY_ERROR_PATTERNS = [
    r"KeyError", r"videoInfoRes", r"itemList", r"aweme_list",
    r"ConnectionError", r"Timeout", r"timed out",
    r"Connection reset", r"Connection refused",
    r"502", r"503", r"504",
    r"临时", r"繁忙", r"请稍后",
]

def is_temporary_backend_error(error_msg: str) -> bool:
    """判断是否为后端临时错误（可重试）。"""
    for pattern in BACKEND_TEMPORARY_ERROR_PATTERNS:
        if re.search(pattern, error_msg, re.IGNORECASE):
            return True
    return False

# ---- 默认配置 ----

DEFAULT_PARSER_API_BASE_URL = "http://192.168.5.116:8000"
DEFAULT_VIDEO_MAX_SIZE_MB = 50
DEFAULT_TIMEOUT_MS = 15000
DEFAULT_RETRY_COUNT = 2
DEFAULT_RETRY_DELAY_MS = 1500
DEFAULT_UNTITLED_TITLE = "未命名"
DEFAULT_UNKNOWN_AUTHOR = "未知作者"
DEFAULT_VIDEO_DELETED_MESSAGE = "该视频已被邪恶势力处理！！！"
BACKEND_TEMPORARY_MESSAGE = "抖音日常抽风请十分钟后再试。。。。"

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

# 需要防盗链 Referer 的 CDN 域名
ANTI_LEECH_DOMAINS = {
    "douyinpic.com", "douyinvod.com", "douyin.com",
    "ixigua.com", "pstatp.com",
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
    return [
        urllib.request.Request(file_url, headers=VIDEO_HEADERS, method="HEAD"),
        urllib.request.Request(
            file_url,
            headers={**VIDEO_HEADERS, "Range": "bytes=0-0"},
            method="GET",
        ),
    ]

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
        self.retry_count = to_positive_int(
            config.get("retry_count"), DEFAULT_RETRY_COUNT
        )
        self.retry_delay_ms = to_positive_int(
            config.get("retry_delay_ms"), DEFAULT_RETRY_DELAY_MS
        )
        self.send_cover = bool(config.get("send_cover", True))
        self.processing_message = str(
            config.get("processing_message") or "ikun解析bot正在处理中。。。"
        ).strip()
        self.video_deleted_message = str(
            config.get("video_deleted_message") or DEFAULT_VIDEO_DELETED_MESSAGE
        ).strip()

        # 打印已启用的平台
        enabled_platforms = [
            name for key, name, _ in PLATFORM_CONFIGS
            if is_platform_enabled(self.config, key)
        ]
        logger.info(
            f"video_parser v0.2.4 initialized: "
            f"api={self.parser_api_base_url} "
            f"max_size={self.video_max_size_mb}MB "
            f"retry={self.retry_count}x{self.retry_delay_ms}ms "
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

        if self.processing_message:
            yield event.plain_result(self.processing_message)

        try:
            video_data = await self.parse_video_share_url(share_url)

            if ensure_list(video_data.get("images")):
                async for result in self._handle_album(event, video_data):
                    yield result
                return
            if "douyin.com" in share_url and str(video_data.get("video_url") or "").strip():
                async for result in self._handle_video(event, video_data, direct=True):
                    yield result
                return
            if str(video_data.get("video_url") or "").strip():
                async for result in self._handle_video(event, video_data, direct=False):
                    yield result
                return

            yield event.plain_result("解析成功，但链接内容好像既不是视频也不是图集呢")

        except VideoDeletedError:
            logger.info(f"video_parser video deleted: {share_url}")
            yield event.plain_result(self.video_deleted_message)
        except BackendTemporaryError as exc:
            logger.warning(f"video_parser backend temporary error after retries: {share_url}: {exc}")
            yield event.plain_result(BACKEND_TEMPORARY_MESSAGE)
        except Exception as exc:
            logger.error(f"video_parser error url={share_url}: {exc}\n{traceback.format_exc()}")
            yield event.plain_result(f"解析失败：{exc}")

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

    async def _handle_video(
        self, event: AstrMessageEvent, data: Dict[str, Any], *, direct: bool
    ):
        tip = "抖音视频解析成功，正在直接发送..." if direct else "视频解析成功，正在发送视频..."
        yield event.plain_result(tip)

        video_url = str(data.get("video_url") or "").strip()

        if self.send_cover:
            cover_url = _pick_first_str(data, "cover_url", "cover", "thumbnail", "thumb", "poster")
            if cover_url:
                try:
                    loop = asyncio.get_running_loop()
                    b64 = await loop.run_in_executor(
                        None, lambda u=cover_url: image_url_to_base64(u, self.request_timeout_ms)
                    )
                    yield event.chain_result([Image(file=b64)])
                except Exception as exc:
                    logger.warning(f"video_parser cover failed: {exc}")
                    try:
                        yield event.chain_result([Image.fromURL(cover_url)])
                    except Exception:
                        pass

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

        chain: List[Any] = []
        title = str(data.get("title") or "").strip()
        author = str(ensure_dict(data.get("author")).get("name") or "").strip()
        if title or author:
            chain.append(Plain(
                f"\n标题: {empty_fallback(title, DEFAULT_UNTITLED_TITLE)}"
                f"\n作者: {empty_fallback(author, DEFAULT_UNKNOWN_AUTHOR)}"
            ))
        chain.append(Video.fromURL(video_url))
        yield event.chain_result(chain)

    # ---- 核心解析逻辑（带重试） ----

    async def parse_video_share_url(self, share_url: str) -> Dict[str, Any]:
        base_url = self.parser_api_base_url.rstrip("/")
        full_url = (
            f"{base_url}/video/share/url/parse"
            f"?url={urllib.parse.quote(share_url, safe='')}"
        )
        loop = asyncio.get_running_loop()

        last_error: Optional[Exception] = None
        max_attempts = self.retry_count + 1  # 1次正常 + N次重试

        for attempt in range(max_attempts):
            try:
                payload, _status = await loop.run_in_executor(
                    None, lambda: request_json(full_url, timeout_ms=self.request_timeout_ms)
                )
                result = ensure_dict(payload)
                code = int(result.get("code") or 0)
                if code != 200:
                    error_msg = str(result.get("msg") or "")
                    # 视频已删除，不重试
                    if is_video_deleted_error(error_msg):
                        raise VideoDeletedError(
                            f"video deleted: {error_msg} (code={code})"
                        )
                    # 后端临时错误，可重试
                    if is_temporary_backend_error(error_msg) and attempt < max_attempts - 1:
                        logger.warning(
                            f"video_parser backend temporary error (attempt {attempt + 1}/{max_attempts}): "
                            f"{error_msg}, retrying in {self.retry_delay_ms}ms..."
                        )
                        await asyncio.sleep(self.retry_delay_ms / 1000.0)
                        continue
                    raise RuntimeError(f"parser error: {error_msg} ({code})")
                return ensure_dict(result.get("data"))
            except VideoDeletedError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < max_attempts - 1 and is_temporary_backend_error(str(exc)):
                    logger.warning(
                        f"video_parser request failed (attempt {attempt + 1}/{max_attempts}): "
                        f"{exc}, retrying in {self.retry_delay_ms}ms..."
                    )
                    await asyncio.sleep(self.retry_delay_ms / 1000.0)
                    continue
                raise

        # 所有重试都失败
        raise BackendTemporaryError(
            f"all {max_attempts} attempts failed: {last_error}"
        ) from last_error

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

class BackendTemporaryError(RuntimeError):
    """后端临时错误，重试后仍然失败。"""
    pass
