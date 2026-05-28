"""
地震卡片展示上下文构建器。
负责把所有地震来源的 EventEnvelope 整理为卡片模板可消费的扁平上下文字典。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ...domain.event_models import EarthquakeEvent, EventEnvelope
from ...services.geo.intensity_service import IntensityCalculator
from ....utils.time_converter import TimeConverter

_TZ_JST = timezone(timedelta(hours=9))
_TZ_UTC = timezone.utc
_TZ_CST = timezone(timedelta(hours=8))

# JMA / P2P 来源集合
_JMA_SOURCES = frozenset({
    "jma_fanstudio", "jma_p2p", "jma_p2p_info",
    "jma_wolfx", "jma_wolfx_info",
})


def _fix_naive_datetime(dt: datetime | None, source_id: str) -> datetime | None:
    """为 naive datetime 附加数据源对应的时区信息。"""
    if dt is None or dt.tzinfo is not None:
        return dt
    if source_id in _JMA_SOURCES:
        return dt.replace(tzinfo=_TZ_JST)
    if source_id == "global_quake":
        return dt.replace(tzinfo=_TZ_UTC)
    return dt.replace(tzinfo=_TZ_CST)


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
    envelope: EventEnvelope,
    options: dict | None = None,
) -> dict:
    """构建通用地震卡片渲染上下文。"""
    options = options or {}
    timezone_str = options.get("timezone", "UTC+8")

    domain = envelope.event
    if not isinstance(domain, EarthquakeEvent):
        raise TypeError("earthquake_card_context requires EarthquakeEvent")

    source_id = envelope.source_id or ""
    metadata = dict(envelope.metadata or {})
    identity = envelope.identity

    mag = domain.magnitude or 0
    if mag < 5:
        mag_class = "bg-low"
    elif mag < 7:
        mag_class = "bg-med"
    else:
        mag_class = "bg-high"

    shock_time = _fix_naive_datetime(domain.occurred_at, source_id)
    time_str = (
        TimeConverter.format_time(shock_time, timezone_str)
        if shock_time
        else "Unknown Time"
    )

    report_num = identity.report_num if identity and identity.report_num else 1
    is_final = identity.is_final if identity else False

    local_est = metadata.get("local_estimation")

    footer_items: list[dict[str, str]] = []
    if local_est and isinstance(local_est, dict):
        dist = local_est.get("distance", 0.0)
        inte = local_est.get("intensity", 0.0)
        place = local_est.get("place_name", "本地")
        desc = IntensityCalculator.get_intensity_description(inte)
        footer_items.append({
            "label": f"{place}预估",
            "value": f"距离震中 {dist:.1f} km，预估最大烈度 {inte:.1f} ({desc})",
        })

    is_jma = source_id in _JMA_SOURCES
    is_eew = source_id in (
        "cea_fanstudio", "cea_pr_fanstudio", "cea_wolfx",
        "cwa_fanstudio", "cwa_wolfx",
        "jma_fanstudio", "jma_p2p", "jma_wolfx",
        "global_quake",
    )

    return {
        "magnitude": f"M{mag:.1f}",
        "mag_class": mag_class,
        "intensity": str(domain.intensity or domain.scale or ""),
        "intensity_label": "震度" if is_jma else "烈度",
        "region": domain.place_name or "未知地点",
        "is_update": report_num > 1,
        "revision": report_num,
        "time_str": time_str,
        "depth": _format_depth(domain.depth),
        "latitude": f"{domain.latitude:.4f}" if domain.latitude is not None else "0.0000",
        "longitude": f"{domain.longitude:.4f}" if domain.longitude is not None else "0.0000",
        "epicenter_str": _format_coordinates(domain.latitude, domain.longitude)
        if domain.latitude is not None and domain.longitude is not None
        else "N/A",
        "event_id": envelope.id or "N/A",
        "source_name": _build_source_name(source_id, metadata, domain, is_eew),
        "footer_items": footer_items,
        "is_eew": is_eew,
    }


def _build_source_name(
    source_id: str,
    metadata: dict,
    domain: EarthquakeEvent,
    is_eew: bool,
) -> str:
    """根据来源构建展示名称。"""
    province = str(getattr(domain, "province", "") or metadata.get("province", "") or "").strip()

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
    envelope: EventEnvelope,
    base_footer: list[dict[str, str]],
    source_id: str,
) -> list[dict[str, str]]:
    """追加来源特有的 footer 条目。"""
    footer = list(base_footer)
    metadata = dict(envelope.metadata or {})
    domain = envelope.event
    identity = envelope.identity

    report_num = identity.report_num if identity and identity.report_num else 1
    is_final = identity.is_final if identity else False

    report_info = f"第 {report_num} 报"
    if is_final:
        report_info += "(最终报)"

    # --- 来源特有字段 ---
    if source_id in ("cea_fanstudio", "cea_pr_fanstudio", "cea_wolfx"):
        footer.append({"label": "报数", "value": report_info})
        province = str(getattr(domain, "province", "") or metadata.get("province", "") or "").strip()
        if province:
            footer.append({"label": "影响区域", "value": province})
        max_pga = metadata.get("max_pga")
        if max_pga is not None:
            footer.append({"label": "最大加速度 (PGA)", "value": f"{float(max_pga):.1f} gal"})

    elif source_id in ("cwa_fanstudio", "cwa_wolfx"):
        footer.append({"label": "报数", "value": report_info})
        impact = str(metadata.get("impact_area") or getattr(domain, "province", "") or "").strip()
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
                scale = getattr(domain, "scale", None)
                warning_type = "警报" if (scale is not None and scale >= 4.5) else "予报"
            footer.append({"label": "种类", "value": warning_type})
        tsunami_val = metadata.get("domestic_tsunami", "")
        if tsunami_val:
            footer.append({"label": "津波", "value": _tsunami_labels.get(str(tsunami_val), str(tsunami_val))})
        # 警报区域
        warn_area = metadata.get("jma_warn_area", "")
        if warn_area:
            footer.append({"label": "警报区域", "value": str(warn_area)})
        else:
            warn_areas = list(metadata.get("jma_warning_areas") or [])
            if warn_areas:
                footer.append({"label": "警报区域", "value": "、".join(warn_areas[:6]) + ("等" if len(warn_areas) > 6 else "")})

    elif source_id in ("jma_p2p_info", "jma_wolfx_info"):
        revision = str(metadata.get("revision") or "").strip()
        if revision:
            footer.append({"label": "订正", "value": revision})
        tsunami_val = metadata.get("domestic_tsunami", "")
        if tsunami_val:
            footer.append({"label": "津波", "value": _tsunami_labels.get(str(tsunami_val), str(tsunami_val))})
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
                if max_s == 45: disp = "5弱"
                elif max_s == 50: disp = "5强"
                elif max_s == 55: disp = "6弱"
                elif max_s == 60: disp = "6强"
                locs = scale_groups[max_s][:5]
                footer.append({"label": "观测点", "value": f"震度{disp}: {'、'.join(locs)}{'等' if len(scale_groups[max_s]) > 5 else ''}"})
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
        max_pga = metadata.get("max_pga")
        if max_pga is not None:
            footer.append({"label": "最大加速度 (PGA)", "value": f"{float(max_pga):.1f} gal"})
        stations = metadata.get("stations") or {}
        used = stations.get("used", 0) if isinstance(stations, dict) else 0
        total = stations.get("total", 0) if isinstance(stations, dict) else 0
        footer.append({"label": "触发测站 (Used/Total)", "value": f"{used} / {total}"})
        loc_err = metadata.get("location_error")
        if isinstance(loc_err, (int, float)):
            footer.append({"label": "定位误差 (Loc Err)", "value": f"{loc_err:.1f} km"})
        else:
            footer.append({"label": "定位误差 (Loc Err)", "value": "N/A"})
        quality_pct = metadata.get("quality_pct")
        footer.append({"label": "数据拟合 (Quality)", "value": f"{quality_pct}%" if quality_pct is not None else "N/A"})

    return footer
