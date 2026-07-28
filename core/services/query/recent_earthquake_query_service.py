"""近期地震信息查询服务。"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

from ....utils.converters import ScaleConverter
from ....utils.time_converter import TimeConverter
from ...services.geo.intensity_service import IntensityService
from ...services.geo.region_service import region_service
from ...services.identity.event_identity import EventIdentityService


OFFICIAL_EARTHQUAKE_SOURCES = (
    "cenc_fanstudio",
    "cenc_wolfx",
    "cwa_fanstudio_report",
    "jma_p2p_info",
    "jma_wolfx_info",
    "usgs_fanstudio",
)

_SOURCE_INSTITUTION = {
    "cenc_fanstudio": "cenc",
    "cenc_wolfx": "cenc",
    "cwa_fanstudio_report": "cwa",
    "jma_p2p_info": "jma",
    "jma_wolfx_info": "jma",
    "usgs_fanstudio": "usgs",
}

_SOURCE_ALIASES = {
    "fan_studio_cenc": "cenc_fanstudio",
    "fan_studio_cwa_report": "cwa_fanstudio_report",
    "fan_studio_usgs": "usgs_fanstudio",
    "p2p_earthquake": "jma_p2p_info",
    "wolfx_cenc_eq": "cenc_wolfx",
    "wolfx_jma_eq": "jma_wolfx_info",
    "china_cenc_earthquake": "cenc_fanstudio",
    "taiwan_cwa_report": "cwa_fanstudio_report",
    "usgs_earthquake": "usgs_fanstudio",
    "japan_jma_earthquake": "jma_p2p_info",
    "中国地震台网（cenc）": "cenc_fanstudio",
    "中国地震台网(cenc)": "cenc_fanstudio",
    "中国地震台网（cenc）：地震测定": "cenc_fanstudio",
    "中国地震台网(cenc)：地震测定": "cenc_fanstudio",
    "中国地震台网 (cenc) - fan": "cenc_fanstudio",
    "中国地震台网地震测定 - wolfx": "cenc_wolfx",
    "台湾中央气象署：地震报告": "cwa_fanstudio_report",
    "台湾中央气象署: 地震报告": "cwa_fanstudio_report",
    "日本气象厅：地震情报": "jma_p2p_info",
    "日本气象厅: 地震情报": "jma_p2p_info",
    "日本气象厅: 地震情报 - p2p": "jma_p2p_info",
    "日本气象厅地震情报 - wolfx": "jma_wolfx_info",
    "美国地质调查局 (usgs)": "usgs_fanstudio",
}

_SOURCE_LABEL = {
    "cenc_fanstudio": "CENC",
    "cenc_wolfx": "CENC",
    "cwa_fanstudio_report": "CWA",
    "jma_p2p_info": "JMA",
    "jma_wolfx_info": "JMA",
    "usgs_fanstudio": "USGS",
}

_SOURCE_DISPLAY_NAME = {
    "cenc_fanstudio": "中国地震台网（CENC）",
    "cenc_wolfx": "中国地震台网（CENC）",
    "cwa_fanstudio_report": "中国台湾地区气象部门（CWA）",
    "jma_p2p_info": "日本气象厅（JMA）",
    "jma_wolfx_info": "日本气象厅（JMA）",
    "usgs_fanstudio": "美国地质调查局（USGS）",
}

_CHANNEL_PRIORITY = {
    "cenc_fanstudio": 0,
    "cenc_wolfx": 1,
    "cwa_fanstudio_report": 0,
    "jma_p2p_info": 0,
    "jma_wolfx_info": 1,
    "usgs_fanstudio": 0,
}

_STABLE_EVENT_ID_SOURCES = {
    "cenc_fanstudio",
    "cwa_fanstudio_report",
    "usgs_fanstudio",
}

_REGION_PRIORITY = {
    "china": ("cenc", "usgs", "jma", "cwa"),
    "taiwan": ("cwa", "usgs", "cenc", "jma"),
    "japan": ("jma", "usgs", "cenc", "cwa"),
    "other": ("usgs", "cenc", "jma", "cwa"),
}

_REGION_LABEL = {
    "china": "中国大陆及港澳地区",
    "taiwan": "中国台湾地区",
    "japan": "日本",
    "other": "其他地区",
}

_TAIWAN_PLACE_KEYWORDS = ("台湾", "臺灣", "台灣")

_LOCATION_CHAR_TRANSLATION = str.maketrans(
    {
        "臺": "台",
        "灣": "湾",
        "峽": "峡",
        "縣": "县",
        "東": "东",
        "蘭": "兰",
        "蓮": "莲",
        "園": "园",
        "雲": "云",
        "義": "义",
        "門": "门",
        "連": "连",
        "綠": "绿",
        "嶼": "屿",
        "濱": "滨",
        "區": "区",
        "鄉": "乡",
        "鎮": "镇",
        "於": "于",
        "離": "离",
        "處": "处",
        "島": "岛",
        "國": "国",
        "県": "县",
        "宮": "宫",
        "愛": "爱",
        "長": "长",
        "広": "广",
        "徳": "德",
        "児": "儿",
        "薩": "萨",
        "豊": "丰",
        "対": "对",
        "馬": "马",
        "葉": "叶",
        "縄": "绳",
        "與": "与",
        "邊": "边",
        "遠": "远",
        "後": "后",
        "發": "发",
    }
)

_CHINA_PLACE_KEYWORDS = (
    "中国",
    "北京",
    "天津",
    "上海",
    "重庆",
    "河北",
    "山西",
    "辽宁",
    "吉林",
    "黑龙江",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "海南",
    "四川",
    "贵州",
    "云南",
    "陕西",
    "甘肃",
    "青海",
    "内蒙古",
    "广西",
    "西藏",
    "宁夏",
    "新疆",
    "香港",
    "澳门",
)

_JAPAN_PLACE_KEYWORDS = (
    "日本",
    "本州",
    "北海道",
    "九州",
    "四国",
    "琉球",
    "小笠原",
    "与那国",
    "與那國",
    "石垣",
    "西表",
    "宮古",
    "宫古",
    "沖縄",
    "冲绳",
    "先島",
    "先岛",
)

_CLUSTER_TIME_SECONDS = 90
_CLUSTER_DISTANCE_KM = 80.0
_CLUSTER_MAGNITUDE_DELTA = 0.8


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _normalize_source_name(value: Any) -> str:
    source_id = str(value or "").strip().lower()
    return _SOURCE_ALIASES.get(source_id, source_id)


def _normalize_display_location_name(value: Any) -> str:
    location = str(value or "").strip()
    if not location:
        return ""

    location = (
        location.replace("沖縄", "冲绳")
        .replace("県沖", "县附近海域")
        .replace("地方沖", "地方附近海域")
        .replace("半島沖", "半岛附近海域")
        .translate(_LOCATION_CHAR_TRANSLATION)
    )
    if location.startswith("中国台湾海峡"):
        location = f"台湾海峡{location[len('中国台湾海峡'):]}"
    elif location.startswith("中国台湾") and not location.startswith("中国台湾地区"):
        suffix = location[len("中国台湾") :]
        location = f"中国台湾地区{suffix.removeprefix('省')}"
    elif location.startswith("中国台湾地区省"):
        location = f"中国台湾地区{location[len('中国台湾地区省'):]}"
    elif location.startswith("台湾省"):
        location = f"中国台湾地区{location[len('台湾省'):]}"
    elif location.startswith("台湾地区"):
        location = f"中国台湾地区{location[len('台湾地区'):]}"
    elif location.startswith("台湾") and not location.startswith("台湾海峡"):
        location = f"中国台湾地区{location[len('台湾'):]}"
    elif location.startswith("香港"):
        location = f"中国香港{location[len('香港'):]}"
    elif location.startswith("澳门"):
        location = f"中国澳门{location[len('澳门'):]}"
    return location


def _coordinate_location(latitude: float, longitude: float) -> str:
    latitude_label = "北纬" if latitude >= 0 else "南纬"
    longitude_label = "东经" if longitude >= 0 else "西经"
    return (
        f"{latitude_label}{abs(latitude):.2f}°、"
        f"{longitude_label}{abs(longitude):.2f}°附近"
    )


def _display_location(candidate: dict[str, Any]) -> str:
    source_id = candidate["source_id"]
    latitude = candidate["latitude"]
    longitude = candidate["longitude"]
    original_location = candidate["place_name"]
    fe_location = region_service.get_fe_name(latitude, longitude)

    if source_id in {
        "cwa_fanstudio_report",
        "jma_p2p_info",
        "jma_wolfx_info",
        "usgs_fanstudio",
    }:
        selected_location = fe_location or original_location
    else:
        selected_location = original_location or fe_location

    normalized_location = _normalize_display_location_name(selected_location)
    lower_location = normalized_location.casefold()
    sensitive_english_names = (
        "taiwan",
        "tibet",
        "hong kong",
        "macao",
        "macau",
        "south china sea",
    )
    contains_latin_letters = any(
        character.isascii() and character.isalpha()
        for character in normalized_location
    )
    if any(name in lower_location for name in sensitive_english_names) or (
        not fe_location and contains_latin_letters
    ):
        normalized_location = _normalize_display_location_name(fe_location)

    return normalized_location or _coordinate_location(latitude, longitude)


def _is_official_record(source_id: str, info_type: str) -> bool:
    normalized_info = str(info_type or "").strip().lower()
    if source_id in {"cenc_fanstudio", "cenc_wolfx"}:
        return "正式" in normalized_info or "reviewed" in normalized_info
    if source_id == "usgs_fanstudio":
        return "正式" in normalized_info or "reviewed" in normalized_info
    if source_id == "cwa_fanstudio_report":
        return True
    if source_id == "jma_p2p_info":
        return normalized_info != "scaleprompt"
    return source_id == "jma_wolfx_info"


def _normalize_candidate(
    record: dict[str, Any],
    *,
    cutoff: datetime,
    now: datetime,
) -> dict[str, Any] | None:
    source_id = _normalize_source_name(
        str(record.get("source_id") or record.get("source") or "")
    )
    if source_id not in _SOURCE_INSTITUTION:
        return None
    if not _is_official_record(source_id, str(record.get("info_type") or "")):
        return None

    occurred_at = EventIdentityService.ensure_utc_datetime(
        record.get("time"), source_id
    )
    magnitude = _safe_float(record.get("magnitude"))
    latitude = _safe_float(record.get("latitude"))
    longitude = _safe_float(record.get("longitude"))
    if (
        occurred_at is None
        or magnitude is None
        or magnitude < 0
        or latitude is None
        or longitude is None
        or not (-90 <= latitude <= 90)
        or not (-180 <= longitude <= 180)
        or occurred_at < cutoff
        or occurred_at > now + timedelta(minutes=5)
    ):
        return None

    return {
        "record": record,
        "source_id": source_id,
        "institution": _SOURCE_INSTITUTION[source_id],
        "event_id": str(
            record.get("real_event_id") or record.get("unique_id") or ""
        ).strip(),
        "occurred_at": occurred_at,
        "magnitude": magnitude,
        "latitude": latitude,
        "longitude": longitude,
        "place_name": str(
            record.get("place_name") or record.get("description") or "未知地点"
        ).strip()
        or "未知地点",
    }


def _is_same_physical_event(
    candidate: dict[str, Any], anchor: dict[str, Any]
) -> bool:
    if (
        candidate["source_id"] == anchor["source_id"]
        and candidate["source_id"] in _STABLE_EVENT_ID_SOURCES
        and candidate["event_id"]
        and anchor["event_id"]
        and candidate["event_id"] != anchor["event_id"]
    ):
        return False

    time_delta = abs(
        (candidate["occurred_at"] - anchor["occurred_at"]).total_seconds()
    )
    if time_delta > _CLUSTER_TIME_SECONDS:
        return False
    if abs(candidate["magnitude"] - anchor["magnitude"]) > _CLUSTER_MAGNITUDE_DELTA:
        return False
    distance = IntensityService.calculate_distance(
        candidate["latitude"],
        candidate["longitude"],
        anchor["latitude"],
        anchor["longitude"],
    )
    return distance <= _CLUSTER_DISTANCE_KM


def _has_stable_id_conflict(
    candidate: dict[str, Any], cluster: list[dict[str, Any]]
) -> bool:
    source_id = candidate["source_id"]
    event_id = candidate["event_id"]
    if source_id not in _STABLE_EVENT_ID_SOURCES or not event_id:
        return False
    return any(
        item["source_id"] == source_id
        and item["event_id"]
        and item["event_id"] != event_id
        for item in cluster
    )


def _cluster_candidates(candidates: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    clusters: list[list[dict[str, Any]]] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (item["occurred_at"], item["magnitude"]),
        reverse=True,
    ):
        matching_cluster = next(
            (
                cluster
                for cluster in clusters
                if not _has_stable_id_conflict(candidate, cluster)
                and _is_same_physical_event(candidate, cluster[0])
            ),
            None,
        )
        if matching_cluster is None:
            clusters.append([candidate])
        else:
            matching_cluster.append(candidate)
    return clusters


def _classify_cluster_region(cluster: list[dict[str, Any]]) -> str:
    latitude = median(item["latitude"] for item in cluster)
    longitude = median(item["longitude"] for item in cluster)
    location_text = " ".join(item["place_name"] for item in cluster)
    if any(keyword in location_text for keyword in _JAPAN_PLACE_KEYWORDS):
        return "japan"
    if any(keyword in location_text for keyword in _TAIWAN_PLACE_KEYWORDS):
        return "taiwan"

    fe_name = region_service.get_fe_name(latitude, longitude, add_suffix=False) or ""
    combined_location_text = f"{location_text} {fe_name}"
    if any(keyword in combined_location_text for keyword in _TAIWAN_PLACE_KEYWORDS):
        return "taiwan"
    if any(keyword in combined_location_text for keyword in _JAPAN_PLACE_KEYWORDS):
        return "japan"
    if any(keyword in combined_location_text for keyword in _CHINA_PLACE_KEYWORDS):
        return "china"

    if 21.5 <= latitude <= 26.5 and 119.0 <= longitude <= 123.5:
        return "taiwan"
    if 24.0 <= latitude <= 46.5 and 127.0 <= longitude <= 146.5:
        return "japan"
    return "other"


def _information_priority(candidate: dict[str, Any]) -> int:
    info_type = str(candidate["record"].get("info_type") or "").lower()
    if "detailscale" in info_type or "各地" in info_type:
        return 4
    if "scaleanddestination" in info_type or "震源・震度" in info_type:
        return 3
    if "destination" in info_type or "震源" in info_type:
        return 2
    if "正式" in info_type or "reviewed" in info_type:
        return 1
    return 0


def _select_cluster_record(
    cluster: list[dict[str, Any]], region: str
) -> dict[str, Any]:
    institution_priority = _REGION_PRIORITY[region]
    return min(
        cluster,
        key=lambda candidate: (
            institution_priority.index(candidate["institution"]),
            _CHANNEL_PRIORITY[candidate["source_id"]],
            -_information_priority(candidate),
            -int(candidate["record"].get("id") or 0),
        ),
    )


def _intensity_display(record: dict[str, Any], institution: str) -> tuple[str, str]:
    level = record.get("level")
    numeric_level = _safe_float(level)
    if numeric_level is None:
        return "---", "int-unknown"

    if institution in {"jma", "cwa"}:
        display = ScaleConverter.format_jma_cwa_scale_display(numeric_level) or "---"
        if numeric_level < 1.5:
            css_class = "int-1"
        elif numeric_level < 2.5:
            css_class = "int-2"
        elif numeric_level < 3.5:
            css_class = "int-3"
        elif numeric_level < 4.5:
            css_class = "int-4"
        elif numeric_level < 5.0:
            css_class = "int-5-weak"
        elif numeric_level < 5.5:
            css_class = "int-5-strong"
        elif numeric_level < 6.0:
            css_class = "int-6-weak"
        elif numeric_level < 6.5:
            css_class = "int-6-strong"
        else:
            css_class = "int-7"
        return display, css_class

    display = f"{numeric_level:g}"
    if numeric_level < 3:
        css_class = "int-1"
    elif numeric_level < 5:
        css_class = "int-2"
    elif numeric_level < 6:
        css_class = "int-3"
    elif numeric_level < 7:
        css_class = "int-4"
    elif numeric_level < 8:
        css_class = "int-5-weak"
    elif numeric_level < 9:
        css_class = "int-5-strong"
    elif numeric_level < 10:
        css_class = "int-6-weak"
    elif numeric_level < 11:
        css_class = "int-6-strong"
    else:
        css_class = "int-7"
    return display, css_class


def _format_earthquake_item(
    candidate: dict[str, Any],
    *,
    region: str,
    display_timezone: str,
) -> dict[str, Any]:
    record = candidate["record"]
    institution = candidate["institution"]
    intensity_display, intensity_class = _intensity_display(record, institution)
    target_timezone = TimeConverter._get_timezone(display_timezone)
    display_time = candidate["occurred_at"].astimezone(target_timezone)

    depth = _safe_float(record.get("depth"))
    if depth is None or depth < 0:
        depth_value = "未知"
        depth_unit = ""
        depth_text = "未知"
        is_text_depth = True
    else:
        depth_value = f"{depth:g}"
        depth_unit = "km"
        depth_text = f"{depth_value} km"
        is_text_depth = False

    return {
        "location": _display_location(candidate),
        "time": display_time.strftime("%Y-%m-%d %H:%M"),
        "magnitude": f"{candidate['magnitude']:.1f}",
        "depth": depth_text,
        "depth_label": "震源深度",
        "depth_value": depth_value,
        "depth_unit": depth_unit,
        "is_text_depth": is_text_depth,
        "intensity_display": intensity_display,
        "intensity_class": intensity_class,
        "intensity_label": (
            "最大震度"
            if institution in {"jma", "cwa"}
            else "最大烈度"
        ),
        "source_id": candidate["source_id"],
        "source_label": _SOURCE_LABEL[candidate["source_id"]],
        "source_name": _SOURCE_DISPLAY_NAME[candidate["source_id"]],
        "region": region,
        "region_label": _REGION_LABEL[region],
        "occurred_at": candidate["occurred_at"].isoformat(),
    }


def select_recent_official_earthquake_records(
    records: list[dict[str, Any]],
    *,
    hours: int,
    count: int,
    display_timezone: str = "UTC+8",
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """筛选并合并近期地震信息，按区域选择适用的机构记录。"""
    active_now = now or datetime.now(timezone.utc)
    if active_now.tzinfo is None:
        active_now = active_now.replace(tzinfo=timezone.utc)
    else:
        active_now = active_now.astimezone(timezone.utc)
    cutoff = active_now - timedelta(hours=max(1, int(hours)))

    candidates = [
        candidate
        for record in records
        if (
            candidate := _normalize_candidate(
                record,
                cutoff=cutoff,
                now=active_now,
            )
        )
        is not None
    ]
    selected: list[tuple[dict[str, Any], str]] = []
    for cluster in _cluster_candidates(candidates):
        region = _classify_cluster_region(cluster)
        selected.append((_select_cluster_record(cluster, region), region))

    selected.sort(
        key=lambda item: (item[0]["magnitude"], item[0]["occurred_at"]),
        reverse=True,
    )
    return [
        _format_earthquake_item(
            candidate,
            region=region,
            display_timezone=display_timezone,
        )
        for candidate, region in selected[: max(1, int(count))]
    ]


async def query_recent_official_earthquakes(
    db,
    *,
    hours: int,
    count: int,
    display_timezone: str = "UTC+8",
) -> list[dict[str, Any]]:
    """从本地数据库查询近期地震信息。"""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max(1, int(hours)))
    records = await db.get_official_earthquake_candidates(
        list(OFFICIAL_EARTHQUAKE_SOURCES),
        cutoff=cutoff,
    )
    return select_recent_official_earthquake_records(
        records,
        hours=hours,
        count=count,
        display_timezone=display_timezone,
        now=now,
    )


def format_recent_earthquake_text(items: list[dict[str, Any]], hours: int) -> str:
    """生成近期地震信息的文本查询结果。"""
    if not items:
        return f"最近 {hours} 小时内暂无符合条件的地震信息"

    lines = [f"🌐 近期地震信息（最近 {hours} 小时，按来源震级值从高到低排列）"]
    for item in items:
        lines.extend(
            [
                "",
                f"• M{item['magnitude']} · 震中：{item['location']}",
                f"   发震时间：{item['time']}",
                f"   信息来源：{item['source_name']}",
                (
                    f"   震源深度：{item['depth']}  "
                    f"{item['intensity_label']}：{item['intensity_display']}"
                ),
            ]
        )
    return "\n".join(lines)


__all__ = [
    "OFFICIAL_EARTHQUAKE_SOURCES",
    "format_recent_earthquake_text",
    "query_recent_official_earthquakes",
    "select_recent_official_earthquake_records",
]
