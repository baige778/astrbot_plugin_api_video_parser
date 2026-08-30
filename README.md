# API 视频/图集解析插件

AstrBot v4 插件，调用外部解析 API 解析短视频/图集分享链接，自动获取直链并直接发送。支持 **27 个平台**，每个平台可独立开关，图集以 base64 逐张发送绕过 CDN 防盗链。

## ✨ 功能

- 🎬 **视频直链解析** — 发送任意支持平台的分享链接，自动获取视频直链并通过 AstrBot 直接发送
- 🖼️ **图集/图文解析** — 支持图集分享链接，一次解析后逐张下载并以 base64 发送（绕过抖音等 CDN 防盗链 403）
- 🔍 **智能平台识别** — 一条综合正则自动匹配 27 个平台，无需手动指定
- 🔌 **平台独立开关** — 27 个平台各自一个开关，可按需关闭不需要的平台
- 🃏 **QQ 小程序卡片提取** — 自动从 QQ 小程序/JSON 消息中提取隐藏的分享链接
- 🖼️ **封面图发送** — 视频附带封面缩略图（可配置开关），自动带 Referer 头处理防盗链
- ⚠️ **视频已删除检测** — 识别视频下架/删除/隐藏等状态，发送自定义提示语
- 📦 **视频大小限制** — 超过上限的视频自动跳过，避免大文件导致发送失败
- ✏️ **自定义提示语** — 处理中提示、视频已删除提示、发送中提示均可自定义内容，并各有独立开关控制是否发送
- 🖼️ **图片容错** — base64 发送失败自动降级为 URL 直链发送
- 📚 **图集合并转发** — 图集自动以「合并转发（聊天记录）」形式发送全部图片，不再逐张发送
- 🎞️ **视频合并发送** — 可开启将封面图、标题作者与视频以「合并转发」形式合并成一条消息发送（开关控制）

## 📋 支持的平台（27 个）

| 平台 | 域名 | 配置键 |
|------|------|--------|
| 抖音 | v.douyin.com, www.douyin.com | `platform_douyin` |
| TikTok | vm.tiktok.com, www.tiktok.com | `platform_tiktok` |
| 快手 | v.kuaishou.com | `platform_kuaishou` |
| B站 | bilibili.com, b23.tv | `platform_bilibili` |
| 小红书 | xhslink.com, www.xiaohongshu.com | `platform_xiaohongshu` |
| 微博 | weibo.com, weibo.cn | `platform_weibo` |
| 西瓜视频 | v.ixigua.com | `platform_xigua` |
| 微视 | isee.weishi.qq.com | `platform_weishi` |
| 皮皮虾 | h5.pipix.com | `platform_pipixia` |
| 皮皮搞笑 | h5.pipigx.com | `platform_pipigx` |
| 火山小视频 | share.huoshan.com | `platform_huoshan` |
| 梨视频 | www.pearvideo.com | `platform_pear` |
| 好看视频 | haokan.baidu.com | `platform_haokan` |
| 虎牙 | v.huya.com | `platform_huya` |
| AcFun | www.acfun.cn | `platform_acfun` |
| 美拍 | meipai.com | `platform_meipai` |
| 逗拍 | doupai.cc | `platform_doupai` |
| 全民K歌 | kg.qq.com | `platform_quanminkge` |
| 6间房 | 6.cn | `platform_sixroom` |
| 新片场 | xinpianchang.com | `platform_xinpianchang` |
| Twitter/X | x.com, twitter.com, t.co | `platform_twitter` |
| 最右 | izuiyou.com | `platform_zuiyou` |
| 央视网 | tv.cctv.com | `platform_cctv` |
| 搜狐视频 | tv.sohu.com | `platform_sohu` |
| 腾讯视频 | v.qq.com | `platform_tencent_video` |
| 绿洲 | weibo.cn | `platform_lvzhou` |
| 度小视 | quanmin.baidu.com | `platform_duxiao` |

> 每个平台的开关在 AstrBot 配置面板中独立控制，默认全部开启。为避免设置页面过长，27 个平台开关已折叠到「更多配置」区域，点击展开即可逐个调整。

## 🧪 平台测试状态

> ⚠️ 插件基于 [parse-video-py](https://github.com/baige778/parse-video-py) 后端 API，除以下已实测平台外，其余平台尚未进行解析功能测试，欢迎反馈。

| 平台 | 内容类型 | 测试状态 |
|------|----------|----------|
| 抖音 | 视频、图集 | ✅ 已测试 |
| 快手 | 视频 | ✅ 已测试 |
| B站 | 视频 | ✅ 已测试 |
| Twitter/X | 图片 | ✅ 已测试 |
| 其他 23 个平台 | — | ❓ 待测试 |

> 未测试不代表不可用，后端 API 原生支持 27 个平台解析，仅尚未在本插件中逐一验证。

## ⚙️ 配置项

### 核心配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `parser_api_base_url` | string | `http://192.168.5.116:8000` | 解析 API 服务地址 |
| `video_max_size_mb` | int | `50` | 视频最大大小（MB），超过不发送 |
| `request_timeout_ms` | int | `15000` | API 请求和文件探测超时（毫秒） |
| `send_cover` | bool | `true` | 是否发送视频封面图 |
| `video_merge_message` | bool | `false` | 是否将封面图/标题作者/视频以「合并转发」形式合并成一条消息发送（关闭则封面、标题、视频分开发送） |
| `send_processing_message` | bool | `true` | 是否发送解析前的处理中提示 |
| `processing_message` | string | `ikun解析bot正在处理中。。。` | 处理中提示语内容（可自定义） |
| `send_video_deleted_message` | bool | `true` | 是否发送视频已删除/下架提示 |
| `video_deleted_message` | string | `该视频已被邪恶势力处理！！！` | 视频已删除提示语内容（可自定义） |
| `send_video_sending_message` | bool | `true` | 是否发送视频发送中提示 |
| `video_sending_message` | string | `视频解析成功，正在发送视频...` | 视频发送中提示语（可自定义） |

### 平台开关（27 个）

配置键格式为 `platform_<key>`，类型为 `bool`，默认值均为 `true`。在 AstrBot 插件配置面板中可直接勾选/取消。

## 🚀 安装

1. AstrBot 插件市场搜索 `astrbot_plugin_api_video_parser` 安装
2. 部署视频解析 API 后端（见下方依赖）
3. 在插件配置中填入 API 地址
4. 重启插件即可使用

## 🔧 依赖

插件本身零依赖（仅使用 Python 标准库），但需要自行部署视频解析 API 后端：

- [parse-video-py](https://github.com/baige778/parse-video-py) — 通过 HTTP 调用 `/video/share/url/parse` 接口
- Docker 部署：`git clone https://github.com/baige778/parse-video-py && cd parse-video-py && docker compose up -d`
- AstrBot v4.x+

## 📝 使用

在聊天中直接发送任意支持平台的分享链接：

```
https://v.douyin.com/xxxxx/
https://b23.tv/xxxxx
https://xhslink.com/xxxxx
```

也支持 QQ 小程序卡片形式分享的链接。

### 处理流程

1. 收到消息 → 提取 URL → 匹配平台 → 检查平台开关
2. 发送处理中提示（如有配置）
3. 调用解析 API 获取视频/图集数据
4. 图集：逐张下载转 base64，统一以「合并转发（聊天记录）」形式发送全部图片
5. 视频：探测文件大小 → 检查上限 → 发送封面图（可选）→ 发送视频直链；可配置以「合并转发」形式将封面/标题/视频合并为一条消息
6. 视频已删除：发送自定义提示语

## 📁 项目结构

```
astrbot_plugin_api_video_parser/
├── __init__.py            # 插件入口，导出 VideoParserPlugin
├── main.py                # 核心逻辑：平台正则、API 调用、图集/视频处理
├── metadata.yaml          # 插件元数据（名称、版本、平台支持）
├── _conf_schema.json      # 配置项 Schema（AstrBot 配置面板使用）
└── README.md
```

## 🔒 隐私说明

- 插件仅在收到分享链接时向配置的 API 后端发送请求
- 无任何遥测、埋点或数据上报
- 图片和视频内容不经过插件服务器，直接从 CDN 发送到聊天平台

## 📄 License

MIT
