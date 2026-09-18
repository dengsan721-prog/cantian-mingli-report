from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from lunar_python import Lunar


ROOT = Path(__file__).resolve().parent
SYSTEM_ROOT = ROOT.parent / "mingli-system"
SYSTEM_SCRIPTS = SYSTEM_ROOT / "scripts"
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
        "prompt": "少开新局，先完成一件事",
        "image": "像一棵不断寻找光线的树，心里总有下一步，也愿意把眼前的事慢慢培育成形",
        "daily": "面对一团乱麻时，常会本能地梳理顺序、安排步骤，希望事情有成长的方向",
        "bond": "在关系里看重共同成长，愿意为未来打算，却也可能把自己的期待变成对身边人的催促",
        "wealth": "更愿意把钱投向学习、孩子、事业基础和看得见的长期积累",
        "restore": "离开嘈杂环境，散步、整理空间或完成一件小事，往往比空想更能恢复状态",
    },
    "火": {
        "strength": "表达、驱动力与影响他人",
        "risk": "节奏过快，判断容易受当下情绪和关注度影响",
        "work": "传播、产品推动、管理协调与现场决策",
        "practice": "重要决定隔夜确认，把热情转成可复核的里程碑",
        "prompt": "重要决定，隔夜再确认",
        "image": "像一盏愿意先亮起来的灯，容易把气氛带热，也希望自己的投入被看见、被回应",
        "daily": "在需要站出来、说清楚、带动大家的时候，往往比独自等待更有精神",
        "bond": "感情里重回应和温度，真正在意时会很热烈；失望也可能来得快，需要给情绪一点降温时间",
        "wealth": "花钱常与体验、体面、效率和照顾身边人有关，热情上来时容易先行动后算账",
        "restore": "规律睡眠、减少连续社交，并把兴奋后的空档留给自己，能让心火慢慢落稳",
    },
    "土": {
        "strength": "承载、执行与稳定关系",
        "risk": "责任持续堆积，不易及时卸载或求助",
        "work": "运营、资源协调、资产管理与长期服务",
        "practice": "列出责任边界，固定复盘哪些任务可以转交或停止",
        "prompt": "分清责任，不必事事亲自承担",
        "image": "像一块愿意托住重量的土地，未必总把话说在前面，却习惯让家里和事情先安稳下来",
        "daily": "别人遇到难处时，常会先考虑怎样把事情接住，久而久之也容易成为大家默认依靠的人",
        "bond": "表达爱更像照顾、承担和守在身边，不太擅长反复解释自己的辛苦",
        "wealth": "对房子、家庭保障、稳定现金流和能留下来的东西更有安全感",
        "restore": "把责任分出去、按时吃饭睡觉，并允许自己暂时不解决所有问题，是重要的恢复方式",
    },
    "金": {
        "strength": "规则、判断与精细控制",
        "risk": "标准过硬，沟通时缺少缓冲和试错空间",
        "work": "技术、财务、法务、工程与质量管理",
        "practice": "把批评改写为标准、证据和下一步，让规则可以被协作",
        "prompt": "标准说清，也给关系留余地",
        "image": "像一把反复打磨的尺，心里有清楚的分寸，愿意把含混的事说准、做实、收好尾",
        "daily": "看见漏洞、失序或不公平时很难装作没发现，常会主动把标准立起来",
        "bond": "关系里重承诺和边界，可靠但不一定柔软；越在意的人，越容易被高标准对待",
        "wealth": "更相信规则、预算、合同和可计算的回报，不喜欢账目含糊或责任不清",
        "restore": "暂时放下评判，做运动、手工或不需要得出结论的事，能让紧绷的头脑松开",
    },
    "水": {
        "strength": "适应、信息流动与深层洞察",
        "risk": "思虑过深，边界容易随环境与关系变化",
        "work": "研究、咨询、贸易、渠道与跨领域连接",
        "practice": "给信息收集设置截止时间，用小实验替代无限推演",
        "prompt": "给思考设一个截止时间",
        "image": "像一条会寻找出口的水流，表面可以安静，心里却一直在观察人情、变化和下一条路",
        "daily": "环境改变时往往能很快读懂气氛，先绕开阻力，再寻找更省力的推进方式",
        "bond": "感情细腻，能听见话外之意，也容易把没有说出口的担忧留在心里反复推演",
        "wealth": "对信息、人脉、流动机会和多种收入渠道较敏感，但选择太多时也容易迟迟不落定",
        "restore": "减少信息输入、靠近水或安静独处，把脑中的念头写下来，会比继续思考更有用",
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


@lru_cache(maxsize=1)
def load_knowledge_foundation() -> dict[str, Any]:
    knowledge_path = SYSTEM_ROOT / "knowledge_base.json"
    database_path = SYSTEM_ROOT / "data" / "mingli_validation.db"
    knowledge: dict[str, Any] = {}
    if knowledge_path.exists():
        knowledge = json.loads(knowledge_path.read_text(encoding="utf-8"))
    rules = {
        item["rule_id"]: {
            "ruleId": item["rule_id"],
            "topic": item["topic"],
            "summary": item["rule_summary"],
        }
        for item in knowledge.get("knowledge_rules", [])
    }
    stats = {
        "publicPeople": 0,
        "publicEvents": 0,
        "chartSnapshots": 0,
        "caseStudies": 0,
        "correctionRecords": 0,
    }
    table_map = {
        "publicPeople": "public_persons",
        "publicEvents": "life_events_public",
        "chartSnapshots": "chart_snapshots",
        "caseStudies": "case_studies",
        "correctionRecords": "correction_records",
    }
    if database_path.exists():
        conn = sqlite3.connect(database_path)
        try:
            for key, table in table_map.items():
                stats[key] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        finally:
            conn.close()
    return {
        "databaseName": knowledge.get("database_name", "命理知识与案例数据库"),
        "version": knowledge.get("version", "unknown"),
        "theorySourceCount": len(knowledge.get("theory_sources", [])),
        "knowledgeRuleCount": len(rules),
        "rules": rules,
        "stats": stats,
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
    foundation = load_knowledge_foundation()
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

    theme_signals: list[str] = []
    if any("财" in item for item in ten_gods):
        theme_signals.append("资源、收入与现实责任")
    if any("官" in item or "杀" in item for item in ten_gods):
        theme_signals.append("规则、职位与外部压力")
    if any("印" in item for item in ten_gods):
        theme_signals.append("学习、经验与被支持的方式")
    if any("食" in item or "伤" in item for item in ten_gods):
        theme_signals.append("表达、技术输出与自我实现")
    if any("比" in item or "劫" in item for item in ten_gods):
        theme_signals.append("自主性、同辈关系与竞争意识")
    theme_text = "、".join(theme_signals) or "责任、选择与自我实现"
    climate_text = "、".join(chart["climate_tags"]) or "节气交界待复核"
    event_samples = "、".join(
        f"{event['date']} 年附近的{event['type']}事件" for event in data["events"][:3]
    )
    event_context = (
        f"你已经提供了 {len(data['events'])} 段可核对的经历，包括{event_samples}。"
        if data["events"]
        else "你暂时没有填写过往经历，所以这一版先从命盘结构讲起，不会拿陌生模板替你虚构已经发生的故事。"
    )

    sections = [
        {
            "id": "portrait",
            "title": "先认识命盘里的这个人",
            "summary": f"{data['name']}的底色不是单一的“强”或“弱”，而是一种以{profile['strength']}为核心、在现实中不断寻找平衡的生命姿态。",
            "scenes": [
                f"如果把这张命盘想成一幅画，{data['name']}更像{profile['image']}。这种气质未必总写在脸上，却常会出现在做决定、承担事情，以及夜深人静独自消化情绪的时候。",
                f"出生于{data['birthplace'] or '尚未补充的出生地'}，换算日期为 {data['solarDate']}。日主为{chart['day_master']}，生在{climate_text}的时节；这让性格里既有{day_element}的本能，也带着{strongest}较显所形成的现实节奏。",
                f"在熟人眼里，可能是一个能把事情接住的人；在自己心里，却未必一直轻松。真正需要留意的不是能力够不够，而是{profile['risk']}时，是否仍允许自己停下来、重新选择。",
            ],
            "listTitle": "这份报告的三个关键词",
            "items": [
                f"天性所长：{profile['strength']}。",
                f"容易承受的压力：{profile['risk']}。",
                f"让自己重新稳下来的方法：{profile['restore']}。",
            ],
            "note": f"当前资料等级为 {quality['level']}，形成{quality['maxReportLevel']}。{hour_boundary}",
        },
        {
            "id": "structure",
            "title": "内在动力：你为什么会这样想、这样做",
            "summary": f"命盘里较醒目的力量落在{strongest}，它会把{dominant_profile['strength']}推到生活前台；相对较少的{weakest}，则提示人生需要后天慢慢补出的另一种能力。",
            "scenes": [
                f"当环境安稳、目标清楚时，{data['name']}通常能把{profile['strength']}变成真正的行动，不只是嘴上想想。越是需要长期投入、耐住过程的事情，越能看出这种底层力量。",
                f"但命盘并不是五种力量越平均越好。{strongest}较显，会带来{dominant_profile['strength']}的优势，也会把“{dominant_profile['risk']}”放大。很多疲惫并非来自做不到，而是来自一直用同一种方式解决所有问题。",
                f"{weakest}相对较少，不等于命里缺什么就一定不好。更现实的理解是：当事情要求与{weakest}相关的节奏、边界或资源时，可能需要借助伙伴、制度和环境，而不是只靠个人意志硬撑。",
            ],
            "listTitle": "专业结构摘要",
            "items": [
                f"五行表层计数：{'，'.join(f'{key}{value}' for key, value in elements.items())}",
                f"十神线索：{'、'.join(ten_gods) if ten_gods else '需待时柱或更多结构补充'}",
                f"合冲标记：{relation_text}",
                f"当前人生主题线索：{theme_text}。",
            ],
            "note": "五行数量只是结构入口，还需结合月令、透干、藏干和合冲判断，不能直接把“少”解释成坏、把“多”解释成好。",
        },
        {
            "id": "character",
            "title": "性格：外人看到的你，与心里的你",
            "summary": f"平常状态下更容易呈现{profile['strength']}；压力升高后，则可能滑向“{profile['risk']}”的另一面。",
            "scenes": [
                f"在一群人讨论事情时，{data['name']}未必总是话最多的那个，但通常会留意事情最后能不能落地。{profile['daily']}。所以别人感受到的，往往是可靠、敏锐或有主见，而不是命盘里那些抽象的五行名称。",
                f"真正累的时候，可能不会立刻说“我撑不住了”，而是继续想办法、继续承担，直到语气变硬、耐心变少，或者忽然什么都不想解释。这个转折点，往往就是“{profile['risk']}”开始出现的时候。",
                f"做重大决定时，内心容易同时出现两股力量：一股希望把事情看得更远、更稳，另一股又想尽快结束不确定。最合适的办法不是逼自己果断，而是{profile['practice']}。",
            ],
            "listTitle": "在人际中的三个观察点",
            "items": [
                "被信任时往往愿意多做一步，但需要确认这一步是主动选择，还是害怕让人失望。",
                "意见不同时，先说明自己真正担心的后果，比直接给结论更容易被理解。",
                f"情绪恢复可尝试：{profile['restore']}。",
            ],
            "note": "性格描述来自日主、季节与可见五行的组合，是倾向而非固定人格，应以本人长期行为为准。",
        },
        {
            "id": "career",
            "title": "事业：什么样的路更容易走出成绩",
            "summary": f"比起追逐一个听起来漂亮的职位名称，更重要的是进入能持续使用“{profile['strength']}”的工作场景。",
            "scenes": [
                f"在工作里，真正能让{data['name']}建立存在感的，通常不是短暂热闹，而是把一件复杂的事逐渐理顺、做成并留下结果。适合长期积累的方向包括{profile['work']}，同时也能借助{dominant_profile['work']}扩大影响。",
                f"一个典型场景是：团队遇到混乱、资源不足或责任无人认领时，{data['name']}容易站出来补位。最初这会带来信任，时间久了却可能变成“所有难事都来找你”。事业上真正的升级，不是承担更多，而是把经验变成方法、规则和可复制的协作。",
                f"当新的机会同时带来更大责任时，先问三个问题：有没有清楚权限、有没有可用资源、成果能否被看见。若三者都模糊，机会很可能只是换一种方式消耗自己；若边界清楚，则更容易形成一次扎实的上升。",
            ],
            "listTitle": "更容易发力的工作场景",
            "items": [
                f"需要{profile['strength']}，并允许长期积累信誉的岗位。",
                "职责、资源和评价标准相对清楚，努力能形成可见成果的团队。",
                f"需要防止的事业惯性：{dominant_profile['risk']}。",
            ],
            "note": "事业方向由命盘能力倾向推演，不等同于唯一职业答案；行业周期、教育经历和现实资源仍是决定条件。",
        },
        {
            "id": "wealth",
            "title": "财富：钱带来的安全感与选择权",
            "summary": f"对{data['name']}而言，钱通常不只是数字，也和责任、自由以及能否照顾重要的人联系在一起。",
            "scenes": [
                f"日常消费与长期安排里，容易表现出这样的偏好：{profile['wealth']}。因此，真正让人安心的未必是账面一时增加，而是知道家里有余地、遇到变化时仍有选择。",
                f"当状态稳定时，会更愿意为长期价值买单；当压力升高、出现“{dominant_profile['risk']}”时，则可能在过度保守与突然决定之间摇摆。大额决定若恰好发生在情绪最满的时候，最好先留一个冷静周期。",
                "财富运势更适合被理解为“管理资源的能力”：能否分清家庭账、事业账和人情账，能否拒绝超出承受力的担保，往往比追问某一年是否暴富更能真正改变结果。",
            ],
            "listTitle": "守住财富感的三个动作",
            "items": [
                "先建立应急储备、保险与负债上限，再讨论扩张和投资。",
                "大额投资、借贷或担保必须独立核验现金流、期限和最坏损失。",
                "帮助家人之前先说清金额、期限和最坏结果，善意才不容易变成长期负担。",
            ],
            "note": "命理只能提供风险偏好与行为模式的观察，不预测具体收益，也不能替代持牌财务、税务或法律意见。",
        },
        {
            "id": "relationships",
            "title": "感情与家庭：爱通常藏在哪些地方",
            "summary": f"表达在意的方式更接近“{profile['bond']}”，爱常常落在具体行动里，却未必总能被对方准确听见。",
            "scenes": [
                f"在亲密关系里，{data['name']}可能更习惯通过做事表达心意：把困难解决、把家照顾好、把未来安排妥当。可另一半有时需要的不是方案，而是一句“我知道你现在不好受”。当行动与情绪错开，明明都在用心，却容易各自觉得没有被理解。",
                f"命盘中的合冲线索为“{relation_text}”。放到生活里，它更像两种节奏在拉扯：既想维持稳定，也会在积累太久后突然要求改变。关系最需要的不是避免争执，而是让小问题在变成旧账之前有机会被说出来。",
                "家庭责任容易成为人生中很重的一部分。照顾父母、伴侣或孩子时，别把“我来扛”当成唯一答案；让家人知道真实难处、一起分配责任，反而更能保住关系里的温度。",
            ],
            "listTitle": "让关系更舒服的方式",
            "items": [
                "讨论事情前先说感受和需求，再进入解决方案。",
                "把钱、照顾责任、与双方父母的边界提前谈清楚，少靠默认和猜测。",
                "冲突后能否重新靠近，比一次争执谁输谁赢更重要。",
            ],
            "note": "关系章节依据性格结构与合冲线索描写互动倾向，不据单一十神断定婚姻次数、对象吉凶或必然结果。",
        },
        {
            "id": "turning-points",
            "title": "人生转折：变化通常从哪里开始",
            "summary": f"这张命盘更容易在{theme_text}发生重新分配时，感受到明显的人生转弯。",
            "scenes": [
                f"转折未必都以戏剧性的方式到来。它可能先表现为一段时间越来越忙、原有方法开始不够用，随后才变成换工作、搬迁、关系重新定位，或者对“以后要怎样生活”产生新的答案。{event_context}",
                f"当{strongest}的力量被环境放大时，机会与压力往往一起来：一方面更容易被看见、被需要，另一方面也更容易陷入“{dominant_profile['risk']}”。真正决定这次变化是上升还是消耗的，是能否在开始之前谈清资源和边界。",
                f"相对而言，值得主动争取的变化，是那些能让{profile['strength']}成为长期资产的机会；需要谨慎的变化，则是只靠情绪推动、承诺很多却没有实际支撑的选择。",
            ],
            "listTitle": "未来遇到变化时，先观察",
            "items": [
                "新的责任是否同时带来相应权限和资源。",
                "这次选择是在逃离短期情绪，还是靠近长期想要的生活。",
                "三个月后回看，身体、关系和现金流是否仍能承受。",
            ],
            "note": "未接入完整大运起运和流年校验前，本章只判断转折类型，不给出具体年份的确定断语。",
        },
        {
            "id": "wellbeing",
            "title": "身心节律：什么时候最需要照顾自己",
            "summary": "身体常常比语言更早知道压力已经超量，能及时听见这些信号，本身就是一种重要能力。",
            "scenes": [
                f"忙起来时，{data['name']}可能会先把任务完成，再处理自己的疲惫。若长期处在“{dominant_profile['risk']}”的状态，最先变化的未必是能力，而可能是睡眠、耐心、胃口、肩颈紧张或对小事的反应。",
                f"适合的恢复方式不一定复杂：{profile['restore']}。关键不是偶尔彻底休息一天，而是让身体每天都能收到“事情已经结束”的信号。",
                "如果某段时间总觉得提不起精神或持续不适，不必把它解释成运势不好。先排除医学问题，再调整作息、工作量和关系压力，往往比寻找一个神秘原因更有效。",
            ],
            "listTitle": "可以从今天开始的小观察",
            "items": [
                "连续四周记录睡眠、情绪、运动和工作负荷，看见压力真正来自哪里。",
                "把休息写进日程，而不是等所有事情做完才允许自己停下。",
                "出现持续或明显不适时，及时接受正规检查和专业治疗。",
            ],
            "note": "本章只依据传统五行偏性讨论生活节律，不对应具体器官疾病，也不构成诊断或治疗建议。",
        },
        {
            "id": "review",
            "title": "还有哪些信息，能让这份报告更像你",
            "summary": "资料不完整并不代表这份报告没有价值，只意味着有些远景需要留白，等真实经历来慢慢校正。",
            "scenes": [
                "命理最容易犯的错误，是在资料不足时仍把话说满。这里把缺口写出来，不是把责任推给填写者，而是让你知道哪些部分可以放心读，哪些部分更适合当作一个等待验证的方向。",
                "如果以后想继续完善，可以回忆几件有明确年月的大事：升学或工作转折、结婚生子、搬迁、明显破财、疾病手术、亲人变化。它们不是为了证明命理一定正确，而是用来排除不符合真实人生的解释。",
            ],
            "listTitle": "目前还可以补充",
            "items": quality["reasonText"] or ["资料已达到当前模型最高等级，后续只需保留原始凭证并记录新发生的事件。"],
            "note": "系统不会因为缺少信息而自动编造时辰，也不会把后来发生的事偷偷改写成事先已经预测。",
        },
        {
            "id": "actions",
            "title": "写给未来十二个月的几句话",
            "summary": f"这一年不必急着变成另一个人，更值得做的是把{profile['strength']}用在真正重要的地方，同时照顾好容易被忽略的自己。",
            "scenes": [
                f"事业上，可以选一件愿意持续做一年的事，不求立刻轰动，但要能留下作品、方法或信誉。方向可围绕{profile['work']}展开，每三个月回看一次，而不是每天怀疑一次。",
                f"关系里，试着让重要的人更早知道你的真实感受。不是等到承担太多才说累，也不是等到失望太久才说在意。对{data['name']}而言，表达软弱并不会削弱可靠，反而会让别人终于有机会靠近。",
                f"当生活再次出现“{profile['risk']}”的迹象时，把它当作提醒，而不是失败。停一下、减一件事、重新安排边界，可能就是这一年最实际的转运方式。",
            ],
            "listTitle": "留给自己的四个约定",
            "items": [
                f"事业：围绕“{profile['work']}”选择一项连续投入十二个月的能力建设。",
                f"身心：用“{profile['restore']}”建立固定的恢复仪式。",
                "财务：重大决定至少隔夜，并和可信任的人核对最坏结果。",
                "复盘：每季度记录一次重要选择及结果，让未来的判断越来越贴近真实的自己。",
            ],
            "note": "这些建议是低风险、可执行的生活方案，不是保证结果的开运承诺。",
        },
    ]

    technical_cues = {
        "portrait": f"四柱为{'、'.join(pillars)}；日主{chart['day_master']}，月令{chart['month_command']}，季节标记为{climate_text}。",
        "structure": f"表层五行以{strongest}较显、{weakest}相对较少；十神可见{'、'.join(ten_gods) if ten_gods else '三柱基础信息'}。",
        "character": f"以{day_element}日主为性情轴，结合{strongest}的显性作用观察稳定状态与压力状态的切换。",
        "career": f"事业判断取{profile['strength']}为能力主线，同时观察{theme_text}怎样落进职责、资源和协作。",
        "wealth": f"财富部分从财星线索、资源承接方式与{dominant_profile['risk']}的行为风险共同研判。",
        "relationships": f"关系部分参考日主表达方式与合冲线索：{relation_text}。",
        "turning-points": f"转折类型由十神主题、合冲结构与 {quality['eventCount']} 项已知事件共同限定，不越级指定年份。",
        "wellbeing": f"身心观察以{climate_text}的寒暖燥湿和{strongest}较显的生活偏性为线索。",
        "review": f"资料等级 {quality['level']}；当前有 {len(quality['reasonCodes'])} 项证据边界需要保留。",
        "actions": "行动建议遵循低风险、可执行、可复盘原则，覆盖事业、财务、关系、健康与环境。",
    }
    deep_insights = {
        "portrait": f"真正贯穿{data['name']}人生的，不是必须证明自己多能扛，而是学会选择什么值得扛、什么应该放下。",
        "structure": f"{strongest}带来的优势已经足够明显，下一阶段的成长不在于继续加强同一种能力，而在于让{weakest}所代表的节奏通过制度、伙伴和环境进入生活。",
        "character": "很多时候，所谓性格问题并不是脾气，而是一个人长期用最擅长的方式保护自己。看见保护背后的担心，改变才不会变成自我否定。",
        "career": "事业真正的分水岭，通常不是又接下一个任务，而是能否把个人经验变成别人也能使用的方法。那一刻，辛苦才开始沉淀为位置。",
        "wealth": "钱最深的作用不是证明成功，而是让人在家庭责任、个人选择和未来不确定之间保留余地。边界清楚，财富才会变成安全感。",
        "relationships": "关系里的难题常常不是不爱，而是一个人在用行动表达，另一个人在等待情绪回应。把爱翻译成对方听得懂的语言，比争论谁付出更多重要。",
        "turning-points": "人生转弯前往往先出现一种旧办法已经不够用的感觉。别急着把不适当成坏运，它也可能是在提醒：新的身份需要新的边界和能力。",
        "wellbeing": "身体不是拖累目标的部分，而是所有目标能够持续的前提。真正有效的自律，也包括在消耗越界之前停下来。",
        "review": "一份诚实的报告会承认自己不知道什么。保留空白不是不专业，而是让未来发生的真实生活仍有权修正今天的判断。",
        "actions": "所谓转运，很多时候不是等待外界突然改变，而是在同样的处境里，开始做出更符合自己长期利益的选择。",
    }
    evidence_map = {
        "portrait": ["KR_001_MONTH_COMMAND_FIRST"],
        "structure": ["KR_001_MONTH_COMMAND_FIRST"],
        "character": ["KR_001_MONTH_COMMAND_FIRST"],
        "career": ["KR_005_CASE_VERIFICATION"],
        "wealth": ["KR_007_FINANCE_SAFETY"],
        "relationships": ["KR_005_CASE_VERIFICATION"],
        "turning-points": ["KR_003_TRUE_SOLAR_BOUNDARY", "KR_005_CASE_VERIFICATION"],
        "wellbeing": ["KR_006_HEALTH_SAFETY"],
        "review": ["KR_002_NO_HOUR_NO_FULL_DETAIL", "KR_004_LUNAR_LEAP_MONTH"],
        "actions": ["KR_008_ACTIONABLE_OUTPUT"],
    }
    for section in sections:
        section["technical"] = technical_cues[section["id"]]
        section["insight"] = deep_insights[section["id"]]
        section_evidence = list(evidence_map[section["id"]])
        if data["timePrecision"] != "unknown" and "KR_002_NO_HOUR_NO_FULL_DETAIL" in section_evidence:
            section_evidence.remove("KR_002_NO_HOUR_NO_FULL_DETAIL")
        if data["calendarType"] != "lunar" and "KR_004_LUNAR_LEAP_MONTH" in section_evidence:
            section_evidence.remove("KR_004_LUNAR_LEAP_MONTH")
        section["evidenceIds"] = section_evidence

    applied_rule_ids = {rule_id for section in sections for rule_id in section["evidenceIds"]}
    if data["timePrecision"] != "unknown":
        applied_rule_ids.discard("KR_002_NO_HOUR_NO_FULL_DETAIL")
    if data["calendarType"] != "lunar":
        applied_rule_ids.discard("KR_004_LUNAR_LEAP_MONTH")
    applied_rules = [
        foundation["rules"][rule_id]
        for rule_id in sorted(applied_rule_ids)
        if rule_id in foundation["rules"]
    ]
    highlights = [
        {"label": "命盘主调", "value": f"{chart['day_master']}日主，{strongest}的力量较显"},
        {"label": "成事方式", "value": profile["strength"]},
        {"label": "关系课题", "value": "先让感受被听见，再一起解决问题"},
        {"label": "当前提醒", "value": profile["prompt"]},
    ]
    return {
        "input": data,
        "chart": {**chart, "pillars": pillars, "elements": elements, "trueSolarVariant": solar_variant},
        "quality": quality,
        "rectification": rectification_candidates(data, quality),
        "report": {
            "title": f"{data['name']}命理综合研判报告",
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "highlights": highlights,
            "sections": sections,
            "foundation": {
                "databaseName": foundation["databaseName"],
                "version": foundation["version"],
                "theorySourceCount": foundation["theorySourceCount"],
                "knowledgeRuleCount": foundation["knowledgeRuleCount"],
                "appliedRules": applied_rules,
                "stats": foundation["stats"],
                "note": "样本规模用于扩大覆盖、发现偏差与保存校验线索，不代表命理预测已经获得科学准确率证明。",
            },
            "disclosure": "这份报告以传统命理结构作人生观察与情境预测。它可以提供另一种理解自己的语言，但不会替你决定人生；所有预测都应等待现实验证，也不能替代医疗、法律、投资等专业意见。",
        },
    }


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
