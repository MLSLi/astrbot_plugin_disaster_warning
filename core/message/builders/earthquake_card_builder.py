"""
通用地震卡片构建器。
负责为所有地震数据源生成灾害预警卡片 HTML 并转换为 Base64 图片消息。
"""

from __future__ import annotations

import base64
import hashlib
import os
from collections.abc import Awaitable, Callable
from typing import Any

from jinja2 import Environment, StrictUndefined
from markupsafe import Markup

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image

from ....utils.map_tile_sources import get_tile_url
from ...domain.event_context import EarthquakeDisplayContext
from ...domain.event_models import EarthquakeEvent, EventEnvelope
from ...services.display.service import build_display_context
from .earthquake_card_context import (
    build_earthquake_card_context,
    build_earthquake_card_footer,
)


class EarthquakeCardBuilder:
    """通用地震卡片构建器，支持所有地震数据源。"""

    def __init__(self, *, plugin_root: str, temp_dir: str, browser_manager):
        self.plugin_root = plugin_root
        self.temp_dir = temp_dir
        self.browser_manager = browser_manager

    async def build(
        self,
        event: EventEnvelope,
        *,
        active_config: dict[str, Any],
        message_format_config: dict[str, Any],
        cache_key_builder: Callable[[EventEnvelope, dict[str, Any], str], str],
        render_with_cache: Callable[
            [str, Callable[[], Awaitable[str | None]]], Awaitable[str | None]
        ],
    ) -> MessageChain | None:
        """构建通用地震卡片消息。"""
        try:
            domain = event.event
            if not isinstance(domain, EarthquakeEvent):
                return None

            source_id = event.source_id or ""
            display_timezone = active_config.get("display_timezone", "UTC+8")
            options = {
                "timezone": display_timezone,
                "local_monitoring": active_config.get("local_monitoring", {}),
            }
            display_context = build_display_context(event, source_id, options)
            if not isinstance(display_context, EarthquakeDisplayContext):
                return None
            context = build_earthquake_card_context(display_context, options)

            # 来源特有 footer
            context["footer_items"] = build_earthquake_card_footer(
                display_context, context["footer_items"]
            )

            # 页面级配置注入
            zoom_level = message_format_config.get("map_zoom_level", 5)
            context["zoom_level"] = zoom_level
            map_source = message_format_config.get("map_source", "PetalMap矢量图亮")
            context["map_source"] = map_source
            context["tile_url"] = get_tile_url(map_source)
            context["tile_subdomains"] = ["1", "2", "3", "4"]

            template_name = message_format_config.get(
                "earthquake_card_template", "Aurora"
            )
            resources_dir = os.path.join(self.plugin_root, "resources")
            template_dir = os.path.join(resources_dir, "card_templates", template_name)
            template_candidates = [
                os.path.join(template_dir, "earthquake_card.html"),
                os.path.join(template_dir, f"{source_id}.html"),
            ]
            if source_id == "global_quake":
                template_candidates.append(
                    os.path.join(template_dir, "global_quake.html")
                )
            template_path = next(
                (path for path in template_candidates if os.path.exists(path)),
                template_candidates[0],
            )

            if not os.path.exists(template_path):
                logger.error(f"[灾害预警] 找不到地震卡片模板: {template_path}")
                return None

            with open(template_path, encoding="utf-8") as f:
                template_content = f.read()

            playwright_mode = active_config.get("message_format", {}).get(
                "playwright_mode", "local"
            )
            if playwright_mode == "remote":
                context["leaflet_js_url"] = (
                    "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
                )
                context["leaflet_css_url"] = (
                    "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
                )
            else:
                leaflet_path = os.path.abspath(
                    os.path.join(resources_dir, "card_templates", "leaflet.js")
                )
                leaflet_css_path = os.path.abspath(
                    os.path.join(resources_dir, "card_templates", "leaflet.css")
                )
                context["leaflet_js_url"] = f"file://{leaflet_path}"
                context["leaflet_css_url"] = f"file://{leaflet_css_path}"

            map_helper_path = os.path.abspath(
                os.path.join(resources_dir, "card_templates", "map_render_helper.js")
            )
            with open(map_helper_path, encoding="utf-8") as hf:
                context["map_render_helper_js"] = Markup(hf.read())

            environment = Environment(autoescape=True, undefined=StrictUndefined)
            template = environment.from_string(template_content)
            html_content = template.render(**context)

            card_cache_key = cache_key_builder(
                event, message_format_config, display_timezone
            )

            async def render_card() -> str | None:
                cache_digest = hashlib.sha256(card_cache_key.encode()).hexdigest()[:20]
                image_filename = f"eq_card_{cache_digest}.png"
                image_path = os.path.join(self.temp_dir, image_filename)
                return await self.browser_manager.render_card(
                    html_content, image_path, selector="#card-wrapper"
                )

            result_path = await render_with_cache(card_cache_key, render_card)
            if result_path and os.path.exists(result_path):
                try:
                    with open(result_path, "rb") as f:
                        b64_data = base64.b64encode(f.read()).decode()
                    return MessageChain([Image.fromBase64(b64_data)])
                except Exception as e:
                    logger.error(f"[灾害预警] 读取地震卡片图片转Base64失败: {e}")
                    return None

            logger.warning(f"[灾害预警] 地震卡片渲染失败 ({source_id})，回退到文本模式")
            return None
        except Exception as e:
            logger.error(f"[灾害预警] 地震卡片构建失败 ({event.source_id}): {e}")
            return None
