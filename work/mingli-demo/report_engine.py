from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from lunar_python import Lunar


ROOT = Path(__file__).resolve().parent
SYSTEM_SCRIPTS = ROOT.parent / "mingli-system" / "scripts"
if str(SYSTEM_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SYSTEM_SCRIPTS))

BRANCH_MIDPOINT_HOURS = {
    "子": 0,
    "丑": 2,
    "寅": 4,
    "卯": 6,
    "辰": 8,
    "巳": 10,
    "午": 12,
    "未": 14,
    "申": 16,
    "酉": 18,
    "戌": 20,
    "亥": 22,
}

STEM_ELEMENT = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}

BRANCH_ELEMENT = {
    "寅": "木", "卯": "木", "巳": "火", "午": "火",
    "辰": "土", "戌": "土", "丑": "土", "未": "土",
    "申": "金", "酉": "金", "亥": "水", "子": "水",
}

ELEMENT_PROFILE = {
    "木": {
        "strength": "规划、生长与建立秩序",
        "risk": "目标铺得过多，推进速度超过资源承载",
        "work": "长期项目、教育策划、组织建设与产品培育",
        "practice": "每季度只保留一项主目标，用完成率代替启动数量",
    },
    "火": {
        "strength": "表达、驱动力与影响他人",
        "risk": "节奏过快，判断容易受当下情绪和关注度影响",
        "work": "传播、产品推动、管理协调与现场决策",
        "practice": "重要决定隔夜确认，把热情转成可复核的里程碑",
    },
    "土": {
        "strength": "承载、执行与稳定关系",
        "risk": "责任持续堆积，不易及时卸载或求助",
        "work": "运营、资源协调、资产管理与长期服务",
        "practice": "列出责任边界，固定复盘哪些任务可以转交或停止",
    },
    "金": {
        "strength": "规则、判断与精细控制",
        "risk": "标准过硬，沟通时缺少缓冲和试错空间",
        "work": "技术、财务、法务、工程与质量管理",
        "practice": "把批评改写为标准、证据和下一步，让规则可以被协作",
    },
    "水": {
        "strength": "适应、信息流动与深层洞察",
        "risk": "思虑过深，边界容易随环境与关系变化",
        "work": "研究、咨询、贸易、渠道与跨领域连接",
        "practice": "给信息收集设置截止时间，用小实验替代无限推演",
    },
}

REASON_TEXT = {
    "CALENDAR_NOT_VERIFIED": "历法与日期来源尚未核验，节气边界附近需要优先复核原始记录。",
    "TIME_UNKNOWN_OR_UNRELIABLE": "出生时刻未知或证据不足，时柱相关结论不成立。",
    "TIME_APPROXIMATE": "出生时间仅为约略时辰，交界时段需要保留相邻时柱。",
    "PLACE_MISSING": "出生地点缺失，无法检查地方时与历史时制。",
    "COORDINATES_MISSING": "出生地经纬度未补齐，暂未完成真太阳时校正。",
    "TIMEZONE_MISSING": "IANA 时区未提供，历史法定时制无法计算。",
    "HISTORICAL_TIME_STANDARD_NOT_VERIFIED": "出生当年的法定时制尚未核验。",
    "FEWER_THAN_FIVE_EVENTS": "可核验人生事件少于五项，不足以进行稳健校时。",
    "FEWER_THAN_THREE_EVENT_TYPES": "人生事件类型少于三类，容易产生单一领域偏差。",
}


def _system_imports() -> tuple[Any, Any, Any]:
    from calculate_chart_snapshots import calculate_chart, parse_time
    from time_calibration import true_solar_time

    return calculate_chart, parse_time, true_solar_time


def optional_float(value: Any, field_name: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name}格式不正确") from exc


def classify_time_precision(value: str) -> str:
    if not value or any(word in value for word in ("未知", "不详", "不知道")):
        return "unknown"
    if re.search(r"(?<!\d)([01]?\d|2[0-3]):[0-5]\d(?!\d)", value):
        return "exact"
    if any(branch in value for branch in BRANCH_MIDPOINT_HOURS) or re.search(r"\d{1,2}点", value):
        return "approximate"
    return "unknown"


def normalize_events(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    events: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or "").strip()
        event_type = str(item.get("type") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if not date and not event_type and not summary:
            continue
        if not date or not event_type or not summary:
            raise ValueError("每项人生事件都需要填写日期、类型和说明")
        if not re.match(r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$", date):
            raise ValueError(f"事件日期格式不正确：{date}")
        events.append({"date": date, "type": event_type, "summary": summary})
    return sorted(events, key=lambda event: (event["date"], event["type"]))


def normalize_input(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("请填写姓名")
    calendar_type = payload.get("calendarType")
    if calendar_type not in {"solar", "lunar"}:
        raise ValueError("历法必须为阳历或农历")
    try:
        year = int(payload.get("year"))
        month = int(payload.get("month"))
        day = int(payload.get("day"))
    except (TypeError, ValueError) as exc:
        raise ValueError("请填写完整、有效的出生日期") from exc
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        raise ValueError("出生日期不合法")
    if calendar_type == "solar":
        try:
            datetime(year, month, day)
        except ValueError as exc:
            raise ValueError("阳历出生日期不合法") from exc
        solar_date = f"{year:04d}-{month:02d}-{day:02d}"
    else:
        lunar_month = -month if bool(payload.get("isLeapMonth")) else month
        try:
            solar_date = Lunar.fromYmd(year, lunar_month, day).getSolar().toYmd()
        except Exception as exc:
            raise ValueError("农历日期无法换算，请检查日期和闰月") from exc

    time_text = str(payload.get("timeText") or payload.get("time") or "").strip()
    longitude = optional_float(payload.get("longitude"), "经度")
    latitude = optional_float(payload.get("latitude"), "纬度")
    if longitude is not None and not -180 <= longitude <= 180:
        raise ValueError("经度必须在 -180 到 180 之间")
    if latitude is not None and not -90 <= latitude <= 90:
        raise ValueError("纬度必须在 -90 到 90 之间")
    return {
        "name": name,
        "gender": payload.get("gender") if payload.get("gender") in {"male", "female", "unknown"} else "unknown",
        "calendarType": calendar_type,
        "year": year,
        "month": month,
        "day": day,
        "isLeapMonth": bool(payload.get("isLeapMonth")),
        "solarDate": solar_date,
        "timeText": time_text,
        "timePrecision": classify_time_precision(time_text),
        "birthplace": str(payload.get("birthplace") or "").strip(),
        "longitude": longitude,
        "latitude": latitude,
        "timezone": str(payload.get("timezone") or "").strip() or None,
        "calendarVerified": bool(payload.get("calendarVerified")),
        "timeStandardVerified": bool(payload.get("timeStandardVerified")),
        "events": normalize_events(payload.get("events")),
    }


def quality_assessment(data: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    has_place = bool(data["birthplace"])
    has_geo = data["longitude"] is not None and data["latitude"] is not None and bool(data["timezone"])
    has_time = data["timePrecision"] in {"exact", "approximate"}
    event_types = len({event["type"] for event in data["events"]})
    if not data["calendarVerified"]:
        reasons.append("CALENDAR_NOT_VERIFIED")
    if data["timePrecision"] == "unknown":
        reasons.append("TIME_UNKNOWN_OR_UNRELIABLE")
    elif data["timePrecision"] == "approximate":
        reasons.append("TIME_APPROXIMATE")
    if not has_place:
        reasons.append("PLACE_MISSING")
    if data["longitude"] is None or data["latitude"] is None:
        reasons.append("COORDINATES_MISSING")
    if not data["timezone"]:
        reasons.append("TIMEZONE_MISSING")
    if has_time and not data["timeStandardVerified"]:
        reasons.append("HISTORICAL_TIME_STANDARD_NOT_VERIFIED")
    if len(data["events"]) < 5:
        reasons.append("FEWER_THAN_FIVE_EVENTS")
    if event_types < 3:
        reasons.append("FEWER_THAN_THREE_EVENT_TYPES")

    if (
        data["timePrecision"] == "exact"
        and has_place
        and has_geo
        and data["calendarVerified"]
        and data["timeStandardVerified"]
        and len(data["events"]) >= 5
        and event_types >= 3
    ):
        level, report_level = "L4", "校准四柱报告"
    elif has_time and has_place:
        level, report_level = "L3", "暂定四柱报告"
    elif has_place:
        level, report_level = "L2", "三柱情境报告"
    else:
        level, report_level = "L1", "基础三柱报告"
    return {
        "level": level,
        "maxReportLevel": report_level,
        "reasonCodes": reasons,
        "reasonText": [REASON_TEXT[code] for code in reasons],
        "eventCount": len(data["events"]),
        "eventTypeCount": event_types,
    }


def element_counts(chart: dict[str, Any]) -> dict[str, int]:
    counts = Counter({element: 0 for element in "木火土金水"})
    for key in ("year_pillar", "month_pillar", "day_pillar", "hour_pillar"):
        pillar = chart.get(key)
        if pillar:
            counts[STEM_ELEMENT[pillar[0]]] += 1
            counts[BRANCH_ELEMENT[pillar[1]]] += 1
    return dict(counts)


def true_solar_variant(data: dict[str, Any], chart: dict[str, Any]) -> dict[str, Any] | None:
    if data["longitude"] is None or not data["timezone"] or data["timePrecision"] not in {"exact", "approximate"}:
        return None
    calculate_chart, parse_time, true_solar_time = _system_imports()
    parsed = parse_time(data["timeText"], data["timePrecision"])
    if parsed is None:
        return None
    local_clock = datetime.fromisoformat(f"{data['solarDate']}T{parsed[0]:02d}:{parsed[1]:02d}")
    try:
        solar_clock, correction = true_solar_time(local_clock, data["longitude"], data["timezone"])
    except ValueError:
        return None
    solar_chart = calculate_chart(solar_clock.strftime("%Y-%m-%d"), solar_clock.strftime("%H:%M"), "exact")
    return {
        "apparentSolarTime": solar_clock.isoformat(timespec="minutes"),
        "correctionMinutes": round(correction, 2),
        "hourPillar": solar_chart["hour_pillar"] if solar_chart else None,
        "changesHourPillar": bool(solar_chart and solar_chart["hour_pillar"] != chart.get("hour_pillar")),
    }


def rectification_candidates(data: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    if data["timePrecision"] != "unknown":
        return {"status": "not_required", "candidates": []}
    if quality["eventCount"] < 5 or quality["eventTypeCount"] < 3:
        return {"status": "insufficient_events", "candidates": []}
    calculate_chart, _, _ = _system_imports()
    candidates = []
    for branch, hour in BRANCH_MIDPOINT_HOURS.items():
        chart = calculate_chart(data["solarDate"], f"{hour:02d}:00", "exact")
        candidates.append({
            "branch": branch,
            "hourPillar": chart["hour_pillar"] if chart else None,
            "probability": round(1 / 12, 6),
        })
    return {
        "status": "candidate_only",
        "candidates": candidates,
        "disclosure": "事件资料已达到启动校时的门槛，但当前模型尚未通过盲测校准，因此只展示候选时辰，不替用户选择。",
    }


def generate_report(payload: dict[str, Any]) -> dict[str, Any]:
    data = normalize_input(payload)
    calculate_chart, _, _ = _system_imports()
    chart = calculate_chart(data["solarDate"], data["timeText"], data["timePrecision"])
    if chart is None:
        raise ValueError("无法根据当前资料完成排盘")
    quality = quality_assessment(data)
    solar_variant = true_solar_variant(data, chart)
    elements = element_counts(chart)
    strongest = max(elements, key=elements.get)
    weakest = min(elements, key=elements.get)
    day_element = STEM_ELEMENT[chart["day_pillar"][0]]
    profile = ELEMENT_PROFILE[day_element]
    dominant_profile = ELEMENT_PROFILE[strongest]
    pillars = [chart["year_pillar"], chart["month_pillar"], chart["day_pillar"]]
    if chart.get("hour_pillar"):
        pillars.append(chart["hour_pillar"])
    ten_gods = sorted({
        item
        for tag in chart["ten_god_tags"]
        for item in ([tag.get("stem")] + list(tag.get("branches") or []))
        if item and item != "日主"
    })
    relation_text = "；".join(chart["conflict_combination_tags"]) or "当前柱位未形成需要优先标记的合冲结构"
    if solar_variant:
        hour_boundary = (
            f"真太阳时校正 {solar_variant['correctionMinutes']} 分钟，校正时柱为"
            f"{solar_variant['hourPillar']}。"
        )
        if solar_variant["changesHourPillar"]:
            hour_boundary += "校正前后时柱不同，所有涉及时柱的判断均应并列保留。"
    elif data["timePrecision"] != "unknown":
        hour_boundary = "因缺少完整经纬度或有效时区，当前时柱按出生地法定钟表时暂算。"
    else:
        hour_boundary = "时辰未知，子女、晚景、精确应期等涉及时柱的内容不作确定结论。"

    sections = [
        {
            "id": "basis",
            "title": "资料基础与边界",
            "summary": f"资料等级 {quality['level']}，当前最高可形成{quality['maxReportLevel']}。",
            "items": [
                f"换算后的阳历日期：{data['solarDate']}",
                f"四柱结构：{' · '.join(pillars)}",
                f"日主：{chart['day_master']}；月令：{chart['month_command']}",
                hour_boundary,
            ],
        },
        {
            "id": "structure",
            "title": "命局骨架",
            "summary": f"日主属{day_element}，当前可见结构中{strongest}较显，{weakest}相对较少。",
            "items": [
                f"五行表层计数：{'，'.join(f'{key}{value}' for key, value in elements.items())}",
                f"十神线索：{'、'.join(ten_gods) if ten_gods else '需待时柱或更多结构补充'}",
                f"合冲标记：{relation_text}",
                f"月令气候：{'、'.join(chart['climate_tags']) or '需结合节气边界复核'}",
                "五行数量只作结构索引，不直接等同旺衰、喜忌或人生吉凶。",
            ],
        },
        {
            "id": "character",
            "title": "性格与决策方式",
            "summary": f"传统结构中，{day_element}侧重{profile['strength']}；{strongest}的显性会进一步放大{dominant_profile['strength']}。",
            "items": [
                f"优势场景：当任务需要{profile['strength']}时，更容易形成稳定投入。",
                f"压力场景：需留意{profile['risk']}。",
                f"结构放大项：{dominant_profile['risk']}。",
                f"纠偏动作：{profile['practice']}。",
                "这些描述应与本人长期行为记录交叉验证，不宜把单一标签当成固定人格。",
            ],
        },
        {
            "id": "career",
            "title": "事业与能力配置",
            "summary": f"更适合从{profile['work']}中寻找可积累的角色，并用{dominant_profile['work']}形成协同。",
            "items": [
                "职业选择先看可迁移能力、行业周期与现实资源，再把命理结构作为复盘视角。",
                f"适配任务通常同时要求：{profile['strength']}。",
                f"管理风险集中在：{dominant_profile['risk']}。",
                "每半年记录三项事实：成果、精力消耗、外部反馈，以事实修正职业判断。",
            ],
        },
        {
            "id": "wealth",
            "title": "财富与风险纪律",
            "summary": "财富部分强调可执行的边界，不从单一命局结构推导收益承诺。",
            "items": [
                "先建立应急储备、保险与负债上限，再讨论扩张和投资。",
                "大额投资、借贷或担保必须独立核验现金流、期限和最坏损失。",
                f"当出现“{dominant_profile['risk']}”的状态时，延迟不可逆的财务决定。",
                "命理结论不得替代持牌财务、税务或法律意见。",
            ],
        },
        {
            "id": "relationships",
            "title": "关系与家庭",
            "summary": "关系判断以承担方式、表达习惯与边界协商为主，不凭单一十神断言婚姻结果。",
            "items": [
                f"当前合冲线索：{relation_text}。",
                "把高频矛盾记录为触发情境、各自需求和修复方式，比追问抽象的合不合更有用。",
                "遇到重大关系决定时，同时评估价值观、责任分配、经济透明和冲突修复能力。",
            ],
        },
        {
            "id": "wellbeing",
            "title": "身心节律",
            "summary": "此部分只提供生活节律观察，不构成疾病判断或治疗建议。",
            "items": [
                f"{strongest}较显时，可重点观察与“{dominant_profile['risk']}”同时发生的睡眠、压力和恢复变化。",
                "连续记录睡眠、运动、情绪和工作负荷四周，再据事实调整作息。",
                "出现持续或明显不适时，应使用正规医学检查和专业治疗。",
            ],
        },
        {
            "id": "review",
            "title": "专家质询与缺口",
            "summary": "以下资料缺口决定了哪些结论必须保留弹性。" if quality["reasonText"] else "当前输入已达到本演示模型的最高资料等级。",
            "items": quality["reasonText"] or ["继续保留原始凭证，并用未来事件做前瞻验证，不回写修改旧预测。"],
        },
        {
            "id": "actions",
            "title": "十二个月行动建议",
            "summary": "仅保留低风险、可复盘、能被事实检验的行动。",
            "items": [
                f"事业：围绕“{profile['work']}”选择一项连续投入十二个月的能力建设。",
                f"节律：针对“{dominant_profile['risk']}”设定明确的停止条件和恢复周期。",
                "财务：不依据本报告进行借贷、担保或高风险投资。",
                "校验：每季度记录一项成功、一项失误及其外部条件，用事实修正报告。",
            ],
        },
    ]
    return {
        "input": data,
        "chart": {**chart, "pillars": pillars, "elements": elements, "trueSolarVariant": solar_variant},
        "quality": quality,
        "rectification": rectification_candidates(data, quality),
        "report": {
            "title": f"{data['name']}命理综合研判报告",
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "sections": sections,
            "disclosure": "本报告由传统命理规则与资料质量模型生成，适合文化研究和个人复盘，不是经科学验证的预测工具，也不替代医疗、法律、投资等专业意见。",
        },
    }


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
