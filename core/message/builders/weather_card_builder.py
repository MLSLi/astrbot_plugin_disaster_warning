"""
气象预警卡片构建器。
负责把气象预警领域事件渲染为卡片图片并转换为 Base64 图片消息。
"""

from __future__ import annotations

import base64
import os
from collections.abc import Awaitable, Callable
from typing import Any

from jinja2 import Template

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image

from ...domain.event_models import EventEnvelope, WeatherEvent
from ..presenters.weather_constants import (
    COLOR_LEVEL_EMOJI,
    SORTED_WEATHER_TYPES,
    WEATHER_EMOJI_MAP,
)


class WeatherCardBuilder:
    """气象预警卡片构建器。"""

    def __init__(self, *, plugin_root: str, temp_dir: str, browser_manager):
        self.plugin_root = plugin_root
        self.temp_dir = temp_dir
        self.browser_manager = browser_manager

    @staticmethod
    def _build_context(
        event: EventEnvelope,
        options: dict | None = None,
    ) -> dict:
        """构建气象卡片渲染上下文。"""
        options = options or {}
        domain = event.event
        if not isinstance(domain, WeatherEvent):
            raise TypeError("Weather card context requires WeatherEvent")

        title = domain.title or ""
        headline = domain.headline or ""
        metadata = dict(event.metadata or {})

        # 匹配文本候选集：对齐 WeatherAlertPresenter，覆盖 weather_type + metadata + title + headline
        match_candidates = [
            metadata.get("weather_type", ""),
            metadata.get("type", ""),
            title,
            headline,
        ]
        match_text = " ".join(str(c).strip() for c in match_candidates if str(c).strip())

        emoji = "⛈️"
        for name in SORTED_WEATHER_TYPES:
            if name in match_text:
                emoji = WEATHER_EMOJI_MAP.get(name, "⛈️")
                break

        color_emoji = ""
        color_level = ""
        # 颜色等级候选集：对齐 WeatherAlertPresenter，覆盖 severity_color + title + headline
        color_candidates = [metadata.get("severity_color", ""), title, headline]
        for color, icon in COLOR_LEVEL_EMOJI.items():
            if any(color and color in str(c) for c in color_candidates if c):
                color_emoji = icon
                color_level = color
                break

        color_key_map = {"红色": "red", "橙色": "orange", "黄色": "yellow", "蓝色": "blue", "白色": "white"}

        from ....utils.time_converter import TimeConverter

        timezone_str = options.get("timezone", "UTC+8")
        time_str = (
            TimeConverter.format_time(domain.effective_at, timezone_str)
            if domain.effective_at
            else "Unknown Time"
        )

        description = metadata.get("description", "")
        max_len = options.get("max_description_length", 512)
        if max_len > 0 and len(description) > max_len:
            description = description[: max_len - 3] + "..."

        glow_class = "glow-high"
        if color_level == "黄色":
            glow_class = "glow-med"
        elif color_level in ("蓝色", "白色"):
            glow_class = "glow-low"

        footer_items = []
        if headline and headline != title:
            footer_items.append({"label": "副标题", "value": headline})

        return {
            "source_name": "中国气象局",
            "emoji": emoji,
            "title": title or headline or "气象预警",
            "color_emoji": color_emoji,
            "color_level": color_level,
            "color_key": color_key_map.get(color_level, "white"),
            "description": description,
            "time_str": time_str,
            "glow_class": glow_class,
            "event_id": event.id or "N/A",
            "footer_items": footer_items,
        }

    async def build(
        self,
        event: EventEnvelope,
        *,
        active_config: dict[str, Any],
        weather_config: dict[str, Any],
        cache_key_builder: Callable[[EventEnvelope, dict[str, Any], str], str],
        render_with_cache: Callable[
            [str, Callable[[], Awaitable[str | None]]], Awaitable[str | None]
        ],
    ) -> MessageChain | None:
        """构建气象预警卡片消息。"""
        try:
            domain = event.event
            if not isinstance(domain, WeatherEvent):
                return None

            display_timezone = active_config.get("display_timezone", "UTC+8")
            max_desc_len = weather_config.get("max_description_length", 512)
            options = {
                "timezone": display_timezone,
                "max_description_length": max_desc_len,
            }
            context = self._build_context(event, options)

            template_name = weather_config.get("weather_card_template", "Aurora")
            resources_dir = os.path.join(self.plugin_root, "resources")
            template_path = os.path.join(
                resources_dir, "card_templates", template_name, "weather_card.html"
            )

            if not os.path.exists(template_path):
                logger.error(f"[灾害预警] 找不到气象卡片模板: {template_path}")
                return None

            with open(template_path, encoding="utf-8") as f:
                template_content = f.read()

            template = Template(template_content)
            html_content = template.render(**context)

            card_cache_key = cache_key_builder(event, weather_config, display_timezone)

            async def render_card() -> str | None:
                image_filename = f"weather_card_{event.id}_1.png"
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
                    logger.error(f"[灾害预警] 读取气象卡片转Base64失败: {e}")
                    return None

            logger.warning("[灾害预警] 气象卡片渲染失败，回退到文本模式")
            return None
        except Exception as e:
            logger.error(f"[灾害预警] 气象卡片构建失败: {e}")
            return None
