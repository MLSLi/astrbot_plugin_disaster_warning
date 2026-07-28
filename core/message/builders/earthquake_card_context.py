"""
地震卡片展示上下文构建器。
负责把所有地震来源的 EventEnvelope 整理为卡片模板可消费的扁平上下文字典。
"""

from __future__ import annotations

from datetime import datetime

from ....utils.converters import ScaleConverter
from ....utils.time_converter import TimeConverter
from ...domain.event_context import EarthquakeDisplayContext
from ...services.geo.intensity_service import IntensityCalculator


def _fix_naive_datetime(
    dt: datetime | None, display_context: EarthquakeDisplayContext
) -> datetime | None:
    """为 naive datetime 附加数据源对应的时区信息。"""
    if dt is None or dt.tzinfo is not None:
        return dt
    source_descriptor = display_context.source_descriptor
    source_timezone = (
        source_descriptor.default_timezone if source_descriptor is not None else "UTC"
    )
    return dt.replace(tzinfo=TimeConverter._get_timezone(source_timezone))


def _format_coordinates(latitude: float, longitude: float) -> str:
    lat_dir = "N" if latitude >= 0 else "S"
    lon_dir = "E" if longitude >= 0 else "W"
    return f"{abs(latitude):.2f}°{lat_dir}, {abs(longitude):.2f}°{lon_dir}"


def _format_depth(depth: float | None) -> str:
    if depth is None:
        return "N/A"
    if depth == 0.0:
        return "极浅"
    return f"{depth} km"


_tsunami_labels: dict[str, str] = {
    "None": "无需担心海啸",
    "Unknown": "不明",
    "Checking": "调查中",
    "NonEffective": "预计若干海面变动",
    "Watch": "津波注意报发布中",
    "Warning": "津波警报/大津波警报发布中",
}


def build_earthquake_card_context(
    display_context: EarthquakeDisplayContext,
    options: dict | None = None,
) -> dict:
    """构建通用地震卡片渲染上下文。"""
    options = options or {}
    timezone_str = options.get("timezone", "UTC+8")

    source_id = display_context.source_id or ""
    metadata = dict(display_context.metadata or {})

    magnitude = display_context.magnitude
    magnitude_known = magnitude is not None and magnitude >= 0
    if not magnitude_known or magnitude < 5:
        mag_class = "bg-low"
    elif magnitude < 7:
        mag_class = "bg-med"
    else:
        mag_class = "bg-high"

    shock_time = _fix_naive_datetime(display_context.occurred_at, display_context)
    time_str = (
        TimeConverter.format_time(shock_time, timezone_str)
        if shock_time
        else "未知时间"
    )

    report_num = display_context.report_num or 1
    local_est = display_context.local_estimation

    footer_items: list[dict[str, str]] = []
    if local_est and isinstance(local_est, dict):
        dist = local_est.get("distance", 0.0)
        inte = local_est.get("intensity", 0.0)
        place = local_est.get("place_name", "本地")
        desc = IntensityCalculator.get_intensity_description(inte)
        footer_items.append(
            {
                "label": f"{place}预估",
                "value": f"距离震中 {dist:.1f} km，预估最大烈度 {inte:.1f} ({desc})",
            }
        )

    source_descriptor = display_context.source_descriptor
    intensity_mode = (
        source_descriptor.intensity_mode if source_descriptor is not None else ""
    )
    uses_scale = intensity_mode == "scale"
    intensity_value = (
        display_context.scale
        if display_context.scale is not None
        else display_context.intensity
    )
    intensity_display = (
        ScaleConverter.format_jma_cwa_scale_display(intensity_value)
        if uses_scale
        else str(intensity_value if intensity_value is not None else "")
    )
    is_eew = source_id in (
        "cea_fanstudio",
        "cea_pr_fanstudio",
        "cea_wolfx",
        "cwa_fanstudio",
        "cwa_wolfx",
        "jma_fanstudio",
        "jma_p2p",
        "jma_wolfx",
        "global_quake",
    )

    latitude = display_context.latitude
    longitude = display_context.longitude
    has_coordinates = (
        latitude is not None
        and longitude is not None
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    )

    legacy_pga = "N/A"
    legacy_location_error = "N/A"
    legacy_stations_used = 0
    legacy_stations_total = 0
    legacy_quality_pct = "N/A"
    if source_id == "global_quake":
        if display_context.max_pga is not None:
            legacy_pga = f"{display_context.max_pga:.1f} gal"
        stations = display_context.stations or {}
        if isinstance(stations, dict):
            legacy_stations_used = stations.get("used", 0)
            legacy_stations_total = stations.get("total", 0)
        quality = metadata.get("quality") or {}
        if isinstance(quality, dict):
            location_error = quality.get("err_origin")
            if location_error is None:
                location_error = quality.get("errOrigin")
            if location_error is not None:
                legacy_location_error = f"{float(location_error):.1f} km"
            quality_pct = quality.get("pct")
            if quality_pct is not None:
                legacy_quality_pct = (
                    str(quality_pct)
                    if str(quality_pct).endswith("%")
                    else f"{quality_pct}%"
                )

    return {
        "magnitude": f"M{magnitude:.1f}" if magnitude_known else "M?",
        "mag_class": mag_class,
        "intensity": intensity_display,
        "intensity_label": "震度" if uses_scale else "烈度",
        "region": display_context.title or "未知地点",
        "is_update": report_num > 1,
        "revision": report_num,
        "time_str": time_str,
        "depth": _format_depth(display_context.depth),
        "has_coordinates": has_coordinates,
        "latitude": latitude,
        "longitude": longitude,
        "epicenter_str": _format_coordinates(latitude, longitude)
        if has_coordinates
        else "调查中",
        "event_id": display_context.event_id or "N/A",
        "source_name": _build_source_name(display_context, metadata),
        "footer_items": footer_items,
        "is_eew": is_eew,
        # 兼容仅提供旧 Global Quake 模板的自定义主题。
        "pga": legacy_pga,
        "location_error": legacy_location_error,
        "stations_used": legacy_stations_used,
        "stations_total": legacy_stations_total,
        "quality_pct": legacy_quality_pct,
    }


def _build_source_name(
    display_context: EarthquakeDisplayContext,
    metadata: dict,
) -> str:
    """根据来源构建展示名称。"""
    source_id = display_context.source_id
    province = str(
        display_context.province or metadata.get("province", "") or ""
    ).strip()

    # JMA EEW
    if source_id in ("jma_fanstudio", "jma_p2p", "jma_wolfx"):
        tags = []
        if metadata.get("is_training"):
            tags.append("训练")
        if metadata.get("is_assumption"):
            tags.append("PLUM法假定震源")
        tag_str = f" [{'/'.join(tags)}]" if tags else ""
        return f"日本气象厅 (紧急地震速报){tag_str}"

    # JMA 情报
    if source_id in ("jma_p2p_info", "jma_wolfx_info"):
        info_type = _determine_jma_info_type(metadata)
        return f"日本气象厅 ({info_type})"

    # CEA
    if source_id in ("cea_fanstudio", "cea_pr_fanstudio", "cea_wolfx"):
        if province:
            return f"{province}地震局"
        return "中国地震预警网"

    # CWA EEW
    if source_id in ("cwa_fanstudio", "cwa_wolfx"):
        return "台湾中央气象署"

    # CWA Report
    if source_id == "cwa_fanstudio_report":
        return "台湾中央气象署 (报告)"

    # CENC
    if source_id in ("cenc_fanstudio", "cenc_wolfx"):
        info_type = metadata.get("info_type", "")
        if "正式" in str(info_type) or "reviewed" in str(info_type).lower():
            label = "正式测定"
        elif "自动" in str(info_type) or "automatic" in str(info_type).lower():
            label = "自动测定"
        else:
            label = "自动测定"
        return f"中国地震台网 [{label}]"

    # USGS
    if source_id == "usgs_fanstudio":
        info_type = metadata.get("info_type", "")
        if str(info_type).lower() == "reviewed":
            label = "正式测定"
        else:
            label = "自动测定"
        return f"USGS [{label}]"

    # Global Quake
    if source_id == "global_quake":
        return "Global Quake"

    source_descriptor = display_context.source_descriptor
    if source_descriptor is not None and source_descriptor.display_name:
        return source_descriptor.display_name
    return source_id


def _determine_jma_info_type(metadata: dict) -> str:
    info_type = str(metadata.get("info_type") or "").strip()
    type_map = {
        "ScalePrompt": "震度速报",
        "Destination": "震源相关情报",
        "ScaleAndDestination": "震度・震源相关情报",
        "DetailScale": "各地震度相关情报",
        "Foreign": "远地地震相关情报",
        "Other": "其他情报",
    }
    if info_type in type_map:
        return type_map[info_type]
    if info_type and any("一" <= c <= "鿿" for c in info_type):
        return info_type
    return "震源・震度情报"


def build_earthquake_card_footer(
    display_context: EarthquakeDisplayContext,
    base_footer: list[dict[str, str]],
) -> list[dict[str, str]]:
    """追加来源特有的 footer 条目。"""
    footer = list(base_footer)
    metadata = dict(display_context.metadata or {})
    source_id = display_context.source_id

    report_num = display_context.report_num or 1
    is_final = display_context.is_final

    report_info = f"第 {report_num} 报"
    if is_final:
        report_info += "(最终报)"

    # --- 来源特有字段 ---
    if source_id in ("cea_fanstudio", "cea_pr_fanstudio", "cea_wolfx"):
        footer.append({"label": "报数", "value": report_info})
        province = str(
            display_context.province or metadata.get("province", "") or ""
        ).strip()
        if province:
            footer.append({"label": "影响区域", "value": province})
        max_pga = metadata.get("max_pga")
        if max_pga is not None:
            footer.append(
                {
                    "label": "最大加速度 (PGA)",
                    "value": f"{float(max_pga):.1f} gal",
                }
            )

    elif source_id in ("cwa_fanstudio", "cwa_wolfx"):
        footer.append({"label": "报数", "value": report_info})
        impact = str(
            metadata.get("impact_area") or display_context.province or ""
        ).strip()
        if impact:
            footer.append({"label": "影响区域", "value": impact})

    elif source_id == "cwa_fanstudio_report":
        img = metadata.get("image_uri", "")
        if img:
            footer.append({"label": "报告图片", "value": str(img)})
        smap = metadata.get("shakemap_uri", "")
        if smap:
            footer.append({"label": "等震度图", "value": str(smap)})

    elif source_id in ("jma_fanstudio", "jma_p2p", "jma_wolfx"):
        footer.append({"label": "报数", "value": report_info})
        if metadata.get("is_cancel"):
            footer.append({"label": "状态", "value": "已取消"})
        else:
            warning_type = str(metadata.get("info_type") or "")
            if not warning_type:
                scale = display_context.scale
                warning_type = "警报" if (scale is not None and scale >= 4.5) else "予报"
            footer.append({"label": "种类", "value": warning_type})
        tsunami_val = metadata.get("domestic_tsunami", "")
        if tsunami_val:
            footer.append(
                {
                    "label": "津波",
                    "value": _tsunami_labels.get(str(tsunami_val), str(tsunami_val)),
                }
            )
        # 警报区域
        warn_area = metadata.get("jma_warn_area", "")
        if warn_area:
            footer.append({"label": "警报区域", "value": str(warn_area)})
        else:
            warn_areas = list(metadata.get("jma_warning_areas") or [])
            if warn_areas:
                footer.append(
                    {
                        "label": "警报区域",
                        "value": "、".join(warn_areas[:6])
                        + ("等" if len(warn_areas) > 6 else ""),
                    }
                )
        # 预估震度范围
        warning_ranges = list(metadata.get("jma_warning_area_ranges") or [])
        if warning_ranges:
            footer.append(
                {
                    "label": "预估震度范围",
                    "value": " / ".join(
                        str(item).strip()
                        for item in warning_ranges
                        if str(item).strip()
                    ),
                }
            )

    elif source_id in ("jma_p2p_info", "jma_wolfx_info"):
        revision = str(metadata.get("revision") or "").strip()
        if revision:
            footer.append({"label": "订正", "value": revision})
        tsunami_val = metadata.get("domestic_tsunami", "")
        if tsunami_val:
            footer.append(
                {
                    "label": "津波",
                    "value": _tsunami_labels.get(str(tsunami_val), str(tsunami_val)),
                }
            )
        # 震度观测点
        points = list(metadata.get("jma_points") or [])
        if points:
            scale_groups: dict[int, list[str]] = {}
            for pt in points:
                s = pt.get("scale", 0)
                addr = str(pt.get("addr", "")).strip()
                if addr:
                    scale_groups.setdefault(s, []).append(addr)
            if scale_groups:
                max_s = max(scale_groups.keys())
                disp = str(max_s / 10).replace(".0", "")
                if max_s == 45:
                    disp = "5弱"
                elif max_s == 50:
                    disp = "5强"
                elif max_s == 55:
                    disp = "6弱"
                elif max_s == 60:
                    disp = "6强"
                locs = scale_groups[max_s][:5]
                footer.append(
                    {
                        "label": "观测点",
                        "value": (
                            f"震度{disp}: {'、'.join(locs)}"
                            f"{'等' if len(scale_groups[max_s]) > 5 else ''}"
                        ),
                    }
                )
        comment = str(metadata.get("jma_comment") or "").strip()
        if comment:
            footer.append({"label": "备注", "value": comment})

    elif source_id in ("cenc_fanstudio", "cenc_wolfx"):
        info_type = str(metadata.get("info_type") or "").strip()
        if info_type:
            footer.append({"label": "测定类型", "value": info_type})

    elif source_id == "usgs_fanstudio":
        info_type = str(metadata.get("info_type") or "").strip()
        if info_type:
            footer.append({"label": "测定类型", "value": info_type})

    elif source_id == "global_quake":
        footer.append({"label": "报数", "value": report_info})

        max_pga = display_context.max_pga
        if max_pga is not None:
            footer.append(
                {
                    "label": "最大加速度 (PGA)",
                    "value": f"{float(max_pga):.1f} gal",
                }
            )

        stations = display_context.stations or {}
        used = stations.get("used", 0) if isinstance(stations, dict) else 0
        total = stations.get("total", 0) if isinstance(stations, dict) else 0
        footer.append(
            {"label": "触发测站 (Used/Total)", "value": f"{used} / {total}"}
        )

        # quality 数据：metadata.quality 是 parser 直接注入的嵌套 dict
        meta_quality = metadata.get("quality") or {}
        if not isinstance(meta_quality, dict):
            meta_quality = {}

        # 定位误差：metadata.quality.err_origin → payload.quality.errOrigin
        err_origin = meta_quality.get("err_origin") or meta_quality.get("errOrigin")
        if err_origin is not None:
            footer.append(
                {
                    "label": "定位误差 (Loc Err)",
                    "value": f"{float(err_origin):.1f} km",
                }
            )
        elif isinstance(metadata.get("location_error"), (int, float)):
            footer.append(
                {
                    "label": "定位误差 (Loc Err)",
                    "value": f"{metadata.get('location_error'):.1f} km",
                }
            )
        else:
            footer.append({"label": "定位误差 (Loc Err)", "value": "N/A"})

        # 数据拟合：metadata.quality.pct → payload.quality.pct
        quality_pct = meta_quality.get("pct")
        if quality_pct is not None:
            quality_pct = (
                f"{quality_pct}%"
                if not str(quality_pct).endswith("%")
                else str(quality_pct)
            )
        footer.append(
            {
                "label": "数据拟合 (Quality)",
                "value": str(quality_pct) if quality_pct is not None else "N/A",
            }
        )

    return footer
