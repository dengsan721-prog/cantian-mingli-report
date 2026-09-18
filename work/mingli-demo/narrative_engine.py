from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any


YANG_STEMS = set("甲丙戊庚壬")

TEN_GOD_FAMILIES = {
    "自主驱动": ("比", "劫"),
    "表达创造": ("食", "伤"),
    "资源经营": ("财",),
    "规则责任": ("官", "杀"),
    "学习内化": ("印",),
}

VOICE_NAMES = ("近景观察", "内外反差", "过程追踪", "问题透视", "双场景", "压力测试", "旁观视角", "写给自己")

LEXICAL_CHOICES = {
    "命盘": ("命盘", "盘面", "四柱结构", "出生盘", "这组干支", "盘中线索"),
    "判断": ("判断", "观察", "研判", "理解", "辨认", "评估"),
    "变化": ("变化", "转向", "变动", "局面更新", "阶段转换", "生活转折"),
    "结果": ("结果", "后续", "成效", "落点", "实际回报", "最终走向"),
    "压力": ("压力", "负荷", "紧绷感", "外部要求", "持续消耗", "高压状态"),
}

PARAGRAPH_LEADS = (
    "先把镜头拉近。",
    "从一个细节说起。",
    "换到日常场景里看。",
    "这里有一层反差。",
    "先不急着谈吉凶。",
    "把时间稍微拉长。",
    "从旁观者的位置看。",
    "落回一次具体取舍。",
    "这部分可以这样验证。",
    "有一处很值得留心。",
    "把抽象结构翻译成生活。",
    "先看事情顺利的时候。",
    "再看负荷升高以后。",
    "如果只观察一个瞬间。",
    "换一种问法会更清楚。",
    "这不是一句性格标签。",
)


def _stable_index(seed: str, key: str, size: int) -> int:
    digest = hashlib.sha256(f"{seed}|{key}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % size


def _pick(seed: str, key: str, values: list[str] | tuple[str, ...]) -> str:
    return values[_stable_index(seed, key, len(values))]


def _ordered_sample(seed: str, key: str, values: list[str], count: int) -> list[str]:
    ranked = sorted(values, key=lambda value: hashlib.sha256(f"{seed}|{key}|{value}".encode("utf-8")).hexdigest())
    return ranked[:count]


def _individualize(text: str, seed: str, key: str, *, lead: bool = False) -> str:
    result = text
    for phrase in sorted(LEXICAL_CHOICES, key=len, reverse=True):
        if phrase in result:
            result = result.replace(phrase, _pick(seed, f"report:lex:{phrase}", LEXICAL_CHOICES[phrase]))
    if lead:
        result = f"{_pick(seed, f'{key}:lead', PARAGRAPH_LEADS)}{result}"
    return result


def _ten_god_axis(ten_gods: list[str]) -> tuple[str, str]:
    counts = {
        family: sum(any(marker in god for marker in markers) for god in ten_gods)
        for family, markers in TEN_GOD_FAMILIES.items()
    }
    family = max(counts, key=lambda item: (counts[item], item)) if any(counts.values()) else "综合承接"
    descriptions = {
        "自主驱动": "遇事先确认自己能掌握什么，再决定是否与人并肩",
        "表达创造": "通过说清、做出和展示成果来确认价值",
        "资源经营": "习惯把想法换算成成本、条件与可持续结果",
        "规则责任": "会先看要求、责任和后果，再安排自己的位置",
        "学习内化": "倾向先理解原理、吸收经验，再形成自己的做法",
        "综合承接": "会在自主、规则、资源与表达之间寻找可行平衡",
    }
    return family, descriptions[family]


def _life_stage(year: int) -> tuple[str, str]:
    age = max(0, datetime.now().year - year)
    if age < 13:
        return "成长奠基期", "养育方式、学习兴趣与安全感"
    if age < 25:
        return "身份探索期", "学习选择、离家独立与自我定位"
    if age < 40:
        return "立业展开期", "职业积累、亲密关系与资源边界"
    if age < 60:
        return "结构重整期", "责任分配、事业沉淀与身心续航"
    return "经验回收期", "资产安排、家庭边界与生活质量"


def build_personality_axes(
    chart: dict[str, Any],
    strongest: str,
    weakest: str,
    ten_gods: list[str],
    relation_text: str,
) -> list[dict[str, str]]:
    day_stem = str(chart.get("day_master") or "")[0:1]
    family, family_description = _ten_god_axis(ten_gods)
    has_clash = "冲" in relation_text or "刑" in relation_text
    has_combine = "合" in relation_text
    return [
        {
            "name": "注意方式",
            "value": "先看变化" if strongest in {"水", "木"} else "先看结构",
            "description": "容易先捕捉流动、可能性和人与人之间的变化。" if strongest in {"水", "木"} else "容易先确认边界、次序、资源与可以落地的部分。",
        },
        {
            "name": "决策方式",
            "value": "先定方向" if day_stem in YANG_STEMS else "先辨细节",
            "description": "更适合先形成方向，再在行动中修正。" if day_stem in YANG_STEMS else "更适合把细节和关系想清楚，再作出承诺。",
        },
        {
            "name": "动力来源",
            "value": family,
            "description": family_description + "。",
        },
        {
            "name": "变化节奏",
            "value": "在碰撞中更新" if has_clash else "在连接中整合" if has_combine else "在稳定中递进",
            "description": (
                "重要变化往往先表现为旧安排与新需要发生摩擦。"
                if has_clash
                else "擅长把分散的人和条件逐渐连接成一套安排。"
                if has_combine
                else f"通常需要连续积累，{weakest}相关能力更适合借助环境补足。"
            ),
        },
    ]


def _compose_scenes(seed: str, section_id: str, context: dict[str, str]) -> tuple[list[str], str]:
    name = context["name"]
    style = _stable_index(seed, f"{section_id}:voice", len(VOICE_NAMES))
    setting = _pick(seed, f"{section_id}:setting", context["settings"])
    second_setting = _pick(seed, f"{section_id}:setting-2", list(reversed(context["settings"])))
    core = context["core"]
    behavior = context["behavior"]
    tension = context["tension"]
    evidence = context["evidence"]
    advice = context["advice"]
    counter = context["counter"]
    meaning = context["meaning"]

    packs = [
        [
            f"{setting}，{name}常会{behavior}。这不是一个孤立习惯；从{evidence}看，{core}更像反复出现的底层路径。",
            f"这条路径顺畅时，事情会因为有人肯梳理、承接或推进而变得清楚；一旦连续透支，{tension}便容易悄悄接管判断。外表仍在处理问题，内里却已经没有多少回旋余地。",
            f"更合适的调整不是推翻原来的长处，而是{advice}。{counter}，所以这项判断应放回真实生活里观察，而不是当成一句定论。",
        ],
        [
            f"别人先看到的，往往是{name}{core}的一面；不容易被看见的，是每到{setting}，心里还会经历一轮取舍。{evidence}让这种内外反差变得更明显。",
            f"平稳时，{behavior}可以换来信任和效率；压力上升后，同一种能力却可能转成{tension}。问题并非性格突然变坏，而是最熟悉的办法被使用得太久。",
            f"真正的突破口在于{advice}。同时记得，{counter}；命盘描述的是倾向强弱，不替现实环境作决定。",
        ],
        [
            f"事情刚开始时，{name}多半会{behavior}；到了{setting}，{core}会从一种想法变成具体动作。盘面里的{evidence}，解释了这条过程线为什么常常重复。",
            f"过程的前半段通常很有力量，后半段则容易出现{tension}。若每次都等到明显疲惫才停，长处会逐渐变成别人理所当然的期待。",
            f"下一次走到相似节点，可以先{advice}。{counter}，因此最好把结果记下来，用几次真实反馈判断这条观察是否贴近本人。",
        ],
        [
            f"为什么{name}在{setting}时，会更倾向于{behavior}？一个可检验的解释是：{evidence}共同把注意力推向了{core}。",
            f"另一个需要追问的问题是，这种选择究竟带来掌控感，还是正在制造{tension}。两者在开始时很像，区别往往要到责任、情绪或时间成本累积之后才看得出来。",
            f"判断它是否适合自己的方法很朴素：{advice}。再把“{counter}”视为反证方向；若现实长期相反，就应降低这段研判的权重。",
        ],
        [
            f"把生活分成两个场景：在{setting}时，{name}会{behavior}；换到{second_setting}，同样的{core}可能呈现出完全不同的表情。{evidence}提供的是两者共同的根。",
            f"前一个场景容易积累成就感，后一个场景却可能诱发{tension}。这也是为什么熟人对{name}的评价有时并不一致，他们看见的是同一股力量在不同条件下的两面。",
            f"与其追问哪一面才是真的，不如{advice}。{counter}，环境变化之后，表现方式也完全可能随之改变。",
        ],
        [
            f"给这项倾向做一次压力测试：当{setting}、时间又不宽裕时，{name}很可能仍会选择{behavior}。{evidence}使{core}成为优先反应。",
            f"若局面很快缓解，这会显得可靠而有效；若压力持续，代价就可能变成{tension}。真正要防的不是一次失误，而是长期没有替代策略。",
            f"可以提前设置一个停止条件：{advice}。同时也要记住另一种解释：“{counter}”。这能避免把所有经历都归因于命盘。",
        ],
        [
            f"站在旁观者的位置看，{name}在{setting}中的动作很有辨识度：{behavior}，之后才处理自己的感受。盘面所见的{evidence}，与{core}形成了同一方向的线索。",
            f"旁人可能把这种表现理解为稳、快、强或想得深，却不一定知道它也伴随{tension}。被看见的优势与没有说出口的成本，往往同时存在。",
            f"让两者重新平衡，可以从{advice}开始。至于另一种解释，也要保留：“{counter}”。它应当作为长期复核项，而不是在一份报告里被轻轻带过。",
        ],
        [
            f"写给此刻的{name}：当你再次身处“{setting}”的情境，可能还是会下意识地{behavior}。那份熟练来自{evidence}，也构成了{core}这条人生主线。",
            f"请同时留意，熟练并不等于没有代价。若开始反复出现{tension}，它不是证明你不够好，而是在提醒旧方法已经接近负荷上限。",
            f"这时不妨{advice}。也给另一种解释留下位置，例如“{counter}”，因为真正成熟的自我理解，允许一张命盘被现实修正。",
        ],
    ]
    scenes = [
        _individualize(paragraph, seed, f"{section_id}:scene:{index}", lead=True)
        for index, paragraph in enumerate(packs[style])
    ]
    experiments = [
        "可以做个小实验：下一次身处“{setting}”的情境，先记录自己最早出现的念头，再执行“{advice}”，比较前后差别。",
        "验证这段话不必等很久。回想最近一次{setting}，看{tension}是在事情之前、过程中，还是结束以后出现。",
        "还有一个观察角度：请身边熟悉{name}的人描述一次相关经历，再对照“{core}”是否真的反复出现。",
        "与其直接相信，不如保留一条反例日志。凡是{name}在{setting}中没有{behavior}的时候，都值得单独记下。",
        "把这项倾向放进一周生活里：每天只记一个发生在{setting}附近的决定，周末再看它更接近{core}还是{tension}。",
        "可以给自己设置一个提醒词。每当察觉{tension}，就暂停十分钟，再用“{advice}”重新安排下一步。",
        "若想判断得更准，可以分别请家人和工作伙伴举例；两边都出现{core}，它才更可能是跨场景的稳定倾向。",
        "这部分最好的校验材料不是感受，而是一次具体经过：当时发生什么、{name}怎么做、后来付出了什么成本。",
        "未来三个月只追踪一个指标：在{setting}时，{name}能否在保持{core}的同时，不再滑向{tension}。",
        "也可以反过来问：如果完全不用原来的处理习惯，{name}会担心失去什么？答案常比性格标签更接近核心。",
        "也要保留另一种解释：“{counter}”。只有它仍不能说明的部分，才值得继续留在这份研判里。",
        "这一章的落点很具体：先试行“{advice}”，留下真实结果，再决定是否把它变成长期习惯。",
    ]
    experiment = _pick(seed, f"{section_id}:experiment", experiments).format(**context, setting=setting)
    scenes.append(_individualize(experiment, seed, f"{section_id}:scene:experiment", lead=True))
    signatures = (
        "本章的核对坐标是{evidence}；优先观察“{setting}”中，{core}是否比其他反应更早出现。",
        "若要把这段研判落到本人身上，可以用{evidence}作起点，再检查{setting}时是否反复走向{tension}。",
        "这里不靠笼统形容词成立。盘面给出的坐标是{evidence}，生活中的验证点则是{setting}。",
        "属于{name}的交叉线索在于：{evidence}指向{core}，而{setting}最容易让这股力量显形。",
        "这一章需要同时满足两层证据：结构上见{evidence}，经历中又能在{setting}辨认出相同路径。",
        "把通用描述拿掉以后，留下的个人线索是{evidence}、{setting}与“{core}”三者是否互相印证。",
    )
    signature = _pick(seed, f"{section_id}:signature", signatures).format(**context, setting=setting)
    audit_tails = (
        "后续若发现另一种解释更充分，例如“{counter}”，这条结论就应降级；若“{advice}”确实改善局面，才保留为个人策略。",
        "复核时既要找支持例子，也要寻找{counter}这样的反例；两边都记录，才能避免只挑顺耳的部分。",
        "这条线索暂时只用于提出问题。只有当{core}跨时间、跨场景重复出现，它才配得上更高权重。",
        "下一次记录时，请把当时条件、本人动作和实际代价分开写；这样才能判断{tension}是否真的由同一模式触发。",
        "若连续三次观察都不符合，就不必勉强解释；若相似处境中稳定复现，再把它纳入长期自我管理。",
        "验证标准不是觉得像，而是能否说出一件具体事情，并看见从{core}走向{tension}的完整过程。",
    )
    signature += _pick(seed, f"{section_id}:audit-tail", audit_tails).format(**context, setting=setting)
    scenes.append(_individualize(signature, seed, f"{section_id}:scene:signature", lead=True))
    personal_lenses = (
        "把四个个人坐标叠进本章：{axisAttention}决定先看见什么，{axisDecision}影响怎样落子，{axisDrive}说明为何愿意持续，{axisPace}则提示何时需要换挡。放到“{setting}”里，重点核对它们是否共同走向{core}。",
        "只属于{name}的观察组合是{axisAttention}、{axisDecision}、{axisDrive}和{axisPace}。本章不逐项贴标签，而是看它们在“{setting}”中相遇后，究竟支持{core}，还是更早触发{tension}。",
        "这段研判的个人坐标并非单一性格词：注意端是{axisAttention}，决定端是{axisDecision}，动力端落在{axisDrive}，转向节奏呈现{axisPace}。四者在“{setting}”中的先后次序，才是值得记录的部分。",
        "对{name}来说，同一场“{setting}”会经过四层过滤：先以{axisAttention}接收局面，再按{axisDecision}形成决定，由{axisDrive}维持投入，并以{axisPace}应对后续转折。观察这条链，比笼统评价性格更准确。",
        "本章可以画成一条个人路径：{axisAttention}负责捕捉信号，{axisDecision}负责取舍，{axisDrive}提供后劲，{axisPace}处理变化。当路径顺畅时更接近{core}；卡住时，则要留意{tension}。",
        "若要区分这份报告与一般描述，可以直接检查{name}的四项组合：{axisAttention}是否最先启动，{axisDecision}是否主导选择，{axisDrive}是否支撑坚持，{axisPace}是否决定退出或调整的时机。验证场景就放在“{setting}”。",
        "进入“{setting}”以后，{name}未必只表现出一种倾向。{axisAttention}让某些信息先被看见，{axisDecision}安排回应顺序，{axisDrive}牵引长期投入，而{axisPace}决定遇到阻力时怎样改变。它们共同构成这一章的个人版本。",
        "把观察压缩成一条可复盘的链路：在“{setting}”中，{name}先呈现{axisAttention}，随后以{axisDecision}推进；事情拉长后，{axisDrive}与{axisPace}共同决定能否保留{core}而不滑向{tension}。",
    )
    personal_lens = _pick(seed, f"{section_id}:personal-lens", personal_lenses).format(**context, setting=setting)
    scenes.append(_individualize(personal_lens, seed, f"{section_id}:scene:personal-lens", lead=True))
    tail = sorted(
        range(1, len(scenes)),
        key=lambda index: hashlib.sha256(f"{seed}|{section_id}:scene-order:{index}".encode("utf-8")).hexdigest(),
    )
    order = (0, *tail)
    return [scenes[index] for index in order], VOICE_NAMES[style]


def _section_summary(seed: str, section_id: str, context: dict[str, str]) -> str:
    variants = [
        "这一部分最值得观察的是{core}，以及它如何在现实中逐渐走向{tension}。",
        "命盘提供的不是一个标签，而是一条从{core}到{tension}的变化路径。",
        "真正有辨识度的地方，在于{core}和{tension}常常由同一股力量产生。",
        "与其问自己属于哪一种人，不如看清{core}在什么条件下会变成{tension}。",
        "这张盘在此处呈现出鲜明的两面：一面是{core}，另一面是{tension}。",
        "日常里反复出现的主题，是怎样保留{core}，又不让生活被{tension}拖住。",
        "从盘面到现实，需要重点核对{core}是否稳定存在，以及{tension}是否已经发生。",
        "这一章不急着下结论，先沿着{core}这条线，辨认{tension}出现前的信号。",
    ]
    stage_closers = (
        "放在{stageName}来看，本章会优先联系{stageFocus}。",
        "结合当前的{stageName}，落点主要在{stageFocus}。",
        "此刻的阶段重点是{stageFocus}，因此不把所有方向平均展开。",
        "到了{stageName}，这条线索首先要在{stageFocus}中接受验证。",
        "这一观察会随阶段改变；当前先对照{stageFocus}。",
        "以{stageName}为背景，先看它怎样影响{stageFocus}。",
    )
    text = _pick(seed, f"{section_id}:summary", variants).format(**context)
    text += _pick(seed, f"{section_id}:summary-stage", stage_closers).format(**context)
    text += _pick(seed, f"{section_id}:summary-action", (
        "对应的检验动作是：{advice}。",
        "可以先用“{advice}”做一次小范围验证。",
        "本章建议从“{advice}”开始观察。",
        "实际落点不求多，先试“{advice}”。",
        "是否贴近本人，可以用“{advice}”后的真实反馈来判断。",
        "先实行“{advice}”，再决定是否保留这条结论。",
    )).format(**context)
    anchor = _pick(seed, f"{section_id}:summary-anchor", context["settings"])
    text += f"具体可以从“{anchor}”这类场景开始回看。"
    if section_id == "portrait":
        text += context["stageNarrative"]
        text += context["chartNarrative"]
    return _individualize(text, seed, f"{section_id}:summary")


def _section_insight(seed: str, section_id: str, context: dict[str, str]) -> str:
    variants = [
        "更深一层看，{meaning}。成长并不是删除原来的自己，而是让优势不必再以透支为代价。",
        "这里真正需要被理解的是：{meaning}。当这件事被说清，许多反复出现的难题才有新的解法。",
        "盘面最终指向的并非吉凶二字，而是{meaning}。能觉察这一点，本身就已经改变了选择。",
        "把所有线索放在一起，会得到一个比性格标签更重要的认识：{meaning}。",
        "所谓调整，不是迎合外界，而是明白{meaning}。边界越清楚，长处越能稳定发挥。",
        "如果只记住这一章的一句话，可以是：{meaning}。这比追求一个漂亮结论更接近现实。",
    ]
    stage_tails = [
        "放在{stageName}，这项观察更适合落到{stageFocus}上。",
        "此刻正处于{stageName}，比追求面面俱到更实际的是围绕{stageFocus}安排先后。",
        "结合{stageName}来看，{stageFocus}是检验这条结论是否有用的主要场域。",
        "人生走到{stageName}，同一份{core}更需要在{stageFocus}中找到合适位置。",
        "就当前阶段而言，先把{stageFocus}理顺，比继续扩大目标更有价值。",
        "{stageName}的重点不在证明自己，而在让{stageFocus}形成可以持续的秩序。",
    ]
    text = _pick(seed, f"{section_id}:insight", variants).format(**context)
    text += _pick(seed, f"{section_id}:stage-tail", stage_tails).format(**context)
    return _individualize(text, seed, f"{section_id}:insight")


def _section_note(seed: str, section_id: str, boundary: str) -> str:
    prefixes = (
        "阅读边界：",
        "需要保留的条件是：",
        "这一判断的使用方式：",
        "复核提示：",
        "请把以下条件一并考虑：",
        "本章不越过的边界：",
    )
    text = f"{_pick(seed, f'{section_id}:note', prefixes)}{boundary}"
    return _individualize(text, seed, f"{section_id}:note")


def build_personalized_narrative(
    *,
    data: dict[str, Any],
    chart: dict[str, Any],
    elements: dict[str, int],
    strongest: str,
    weakest: str,
    profile: dict[str, str],
    dominant_profile: dict[str, str],
    ten_gods: list[str],
    relation_text: str,
    theme_text: str,
    climate_text: str,
    event_context: str,
    luck_cycle_context: str,
    quality: dict[str, Any],
    hour_boundary: str,
    pillars: list[str],
) -> dict[str, Any]:
    seed_payload = {
        "name": data["name"],
        "gender": data["gender"],
        "solarDate": data["solarDate"],
        "timeText": data["timeText"],
        "birthplace": data["birthplace"],
        "pillars": pillars,
        "events": data["events"],
    }
    seed = hashlib.sha256(json.dumps(seed_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    axes = build_personality_axes(chart, strongest, weakest, ten_gods, relation_text)
    stage_name, stage_focus = _life_stage(int(data["solarDate"][:4]))
    stage_narrative = {
        "成长奠基期": "这一阶段先不急着把孩子定型。比起预判一生，更值得观察什么环境能唤起兴趣、什么沟通能建立安全感，以及挫折以后能否重新回到尝试之中。",
        "身份探索期": "这一阶段会同时遇到离开熟悉评价、选择学习方向和建立自我边界。报告应帮助本人分清哪些期待来自内心，哪些只是暂时借用了家人或同伴的声音。",
        "立业展开期": "这一阶段常把职业、关系和资源放到同一张桌上。真正的成熟不是每件事都扛住，而是知道哪份责任值得长期投入，哪种合作必须先谈清边界。",
        "结构重整期": "这一阶段关注的已不只是继续向前，而是重新配置时间、体力与责任。能够沉淀的方法要留下，长期消耗却没有回报的角色，则需要被重新协商。",
        "经验回收期": "这一阶段更适合把生活从扩张转向取舍：哪些经验值得传给下一代，哪些责任可以交还，怎样让资产、关系与身体节律共同服务于生活质量。",
    }[stage_name]
    family, family_description = _ten_god_axis(ten_gods)
    event_descriptions = [f"{event['date']} {event['type']}：{event['summary']}" for event in data["events"][:3]]
    event_line = "；".join(event_descriptions) if event_descriptions else event_context
    element_line = "，".join(f"{key}{value}" for key, value in elements.items())
    ten_god_line = "、".join(ten_gods) if ten_gods else "三柱基础信息"
    current_luck = luck_cycle_context or "当前没有足够条件形成可靠的大运时间背景"
    theme_topics = [item for item in theme_text.split("；") if item]
    primary_theme = theme_topics[0]
    supporting_theme = theme_topics[1] if len(theme_topics) > 1 else stage_focus
    chart_values = {
        "name": data["name"],
        "pillars": "、".join(pillars),
        "strongest": strongest,
        "weakest": weakest,
        "family": family,
        "pace": axes[3]["value"],
    }
    chart_narrative = _pick(seed, "chart-narrative", (
        "这份个人坐标以{pillars}为盘面起点：{strongest}较显，{weakest}更适合借助环境补足；动力主线落在{family}，面对转折则接近“{pace}”。后文都从这组交叉线索展开。",
        "把专业底稿压缩来看，{name}的四柱为{pillars}。其中{strongest}提供显性着力点，{weakest}提示补偿方向，{family}牵引长期投入，“{pace}”则描述转弯时的节拍。",
        "先记住一组只用于本报告的坐标：{pillars}构成四柱，{family}是动力重心；{strongest}较容易被看见，{weakest}需要在伙伴、制度或习惯中得到支援。其应变方式更像{pace}。",
        "为什么后文会这样展开？盘面由{pillars}起算，先显出{strongest}的资源，再把{weakest}列为补偿项；十神主题收束到{family}，转折线索呈现{pace}。这些条件共同限定了本次叙事。",
        "属于{name}的底层组合不是单个标签。{pillars}给出结构，{strongest}说明惯用资源，{weakest}指出不宜长期硬撑之处；{family}决定动力方向，而{pace}影响调整旧安排的时机。",
        "从变化的节奏倒推，{pace}是这份盘较醒目的线索；往内看，{family}提供持续动力。再落到五行，{strongest}较显而{weakest}偏少，四柱坐标则是{pillars}。后文据此逐层验证。",
        "本次不从泛泛的性格分类开始，而从{pillars}这组四柱出发。它让{strongest}成为较常用的资源，把{weakest}留作环境补位，并让{family}与{pace}分别回答“为何坚持”和“如何转向”。",
        "若把这份研判画成地图，{pillars}是经纬，{strongest}是常走的路，{weakest}是需要外部路标的地段；{family}提供目的地，“{pace}”说明遇到岔路时通常怎样重新选择。",
    )).format(**chart_values)

    contexts: list[dict[str, Any]] = [
        {
            "id": "portrait", "title": "先认识命盘里的这个人", "listTitle": "这份侧写的四个坐标",
            "core": profile["strength"], "behavior": f"观察局面，并用{profile['strength']}找到着手点", "tension": profile["risk"],
            "evidence": f"{chart['day_master']}日主、{chart['month_command']}月令与{climate_text}",
            "advice": profile["practice"], "counter": "成长经历和家庭角色可能让同一倾向呈现出不同外貌",
            "meaning": "真正稳定的不是某种固定脾气，而是面对世界时反复采用的那套方法",
            "settings": ["第一次进入陌生环境", "家里突然需要有人拿主意", "一项任务没有清楚分工", "独处复盘一天得失", "别人把难题交到手上", "计划临时发生变化"],
            "actions": [f"注意方式：{axes[0]['value']}，{axes[0]['description']}", f"决策方式：{axes[1]['value']}，{axes[1]['description']}", f"动力来源：{axes[2]['value']}，{axes[2]['description']}", f"应变节奏：{axes[3]['value']}，{axes[3]['description']}"],
            "boundary": f"{hour_boundary}画像用于解释倾向，不把人锁定成单一类型。",
        },
        {
            "id": "structure", "title": "内在动力：你为什么会这样想、这样做", "listTitle": "盘面动力的可核对线索",
            "core": f"让{dominant_profile['strength']}成为显性优势", "behavior": f"依靠{strongest}的节奏组织局面",
            "tension": dominant_profile["risk"], "evidence": f"五行表层为{element_line}，{strongest}较显而{weakest}相对少",
            "advice": f"把{weakest}对应的能力交给制度、伙伴或固定流程补足", "counter": "五行数量只是入口，月令、藏干和现实训练会改变实际表现",
            "meaning": "命局的不均衡不是缺陷清单，而是一种有重点的资源配置",
            "settings": ["同时摆着好几件都重要的事", "资源不够却必须继续推进", "需要在速度与质量之间选择", "团队意见彼此冲突", "长期计划进入疲惫期", "旧方法突然失去效果"],
            "actions": [f"显性资源：{strongest}，可发挥{dominant_profile['strength']}。", f"补偿方向：{weakest}，优先借助环境而非硬撑。", f"十神主线：{family}，{family_description}。", f"合冲线索：{relation_text}。", f"当前主题：{theme_text}。"],
            "boundary": "五行多寡不直接等于好坏，仍需结合月令、透干、藏干和合冲判断。",
        },
        {
            "id": "character", "title": "性格：外人看到的你，与心里的你", "listTitle": "稳定状态与压力状态",
            "core": f"以{profile['strength']}建立可靠感", "behavior": "先处理局面，再判断要不要表达自己的感受",
            "tension": profile["risk"], "evidence": f"日主意象“{profile['image']}”与{strongest}的显性力量",
            "advice": profile["restore"], "counter": "教育、职业训练和长期关系会重塑表达方式",
            "meaning": "很多所谓性格问题，其实是一个人长期使用最擅长的方法保护自己",
            "settings": ["会议里出现一段无人回应的沉默", "亲近的人忽然情绪低落", "自己的意见被误解", "承诺快到期限却仍有变数", "需要拒绝一个熟人的请求", "辛苦完成的事没有被看见"],
            "actions": [f"稳定状态：{profile['strength']}。", f"压力信号：{profile['risk']}。", f"恢复入口：{profile['restore']}。", f"决策练习：{profile['practice']}。", "重要沟通先说担心的后果，再给出结论。"],
            "boundary": "性格章节描述的是高频倾向，应以本人长期行为和身边人的稳定反馈复核。",
        },
        {
            "id": "career", "title": "事业：什么样的路更容易走出成绩", "listTitle": "适合积累职业资本的条件",
            "core": f"把{profile['strength']}沉淀成别人可识别的能力", "behavior": f"围绕{profile['work']}寻找可以长期留下成果的位置",
            "tension": f"责任不断增加，却没有同步获得资源，最终出现{dominant_profile['risk']}",
            "evidence": f"十神以{family}为当前主线，主要议题落在{primary_theme}，同时牵动{supporting_theme}",
            "advice": "接受新职责之前写清权限、资源、期限和成果归属", "counter": "行业周期、教育背景和现实机会比命盘标签更直接地影响职业结果",
            "meaning": "事业升级不是被更多事情需要，而是经验开始形成方法、作品和不可轻易替代的位置",
            "settings": ["项目刚接手还没有现成办法", "上级提出一个边界模糊的新任务", "团队在关键节点缺少主心骨", "工作稳定却开始缺乏成长感", "一次合作同时带来机会和额外责任", "准备从执行者走向负责人"],
            "actions": [f"优先场景：{profile['work']}。", f"可积累能力：{profile['strength']}。", "新责任必须同时确认权限和可用资源。", "每季度留下一项作品、方法或可量化成果。", f"防止职业惯性：{dominant_profile['risk']}。"],
            "boundary": "职业方向是能力与环境的匹配建议，不等同于唯一行业或职位答案。",
        },
        {
            "id": "wealth", "title": "财富：钱带来的安全感与选择权", "listTitle": "让资源留下来的具体做法",
            "core": profile["wealth"], "behavior": "先判断这笔资源能否解决现实问题、换来时间或守住重要关系",
            "tension": f"在{dominant_profile['risk']}时作出超出承受力的承诺", "evidence": f"财星及资源主题首先联系{primary_theme}，并与{supporting_theme}互相影响",
            "advice": "把家庭账、事业账和人情账分开，并为大额决定设置冷静期", "counter": "真实收入、负债、家庭责任和金融知识决定最终财务结果",
            "meaning": "财富真正提供的是在责任、选择和不确定之间保留余地",
            "settings": ["家里出现一笔计划外支出", "有人提出借款、合伙或担保", "收入增加后生活标准也跟着抬高", "面对看起来很好的投资机会", "要在眼前享受与长期保障之间选择", "家庭成员对钱怎么用意见不同"],
            "actions": ["先建立应急储备和负债上限。", "大额支出至少经过一次隔夜复核。", "借贷、担保与合伙必须留下清楚书面条件。", f"资源偏好：{profile['wealth']}。", "每季度核对现金流，而不是只看账户余额。"],
            "boundary": "本章只讨论资源行为与风险偏好，不预测具体收益，也不替代持牌财务或法律意见。",
        },
        {
            "id": "relationships", "title": "感情与家庭：爱通常藏在哪些地方", "listTitle": "让关系被彼此听懂",
            "core": profile["bond"], "behavior": "先用行动、安排或解决问题表达在意",
            "tension": "双方都在付出，却因为表达语言不同而各自觉得没有被理解", "evidence": f"日主表达方式与合冲线索“{relation_text}”",
            "advice": "重要讨论先说感受和需求，再一起决定解决办法", "counter": "伴侣性格、共同经历和关系阶段会显著改变互动结果",
            "meaning": "关系里的难处经常不是没有爱，而是付出没有被翻译成对方听得懂的语言",
            "settings": ["伴侣只想被听见而不是立刻得到方案", "家务、金钱或照顾责任长期分配不均", "一句无心的话触发了旧情绪", "双方父母的需要同时出现", "工作很忙却又担心关系变淡", "冲突之后谁都没有先开口"],
            "actions": ["先复述对方的感受，再表达自己的立场。", "提前谈清钱、家务、照顾责任和双方父母的边界。", "冲突后约定重新靠近的时间，不让沉默无限延长。", f"惯常表达：{profile['bond']}。", "每周留一次不解决任务、只交换近况的谈话。"],
            "boundary": "关系结论只描述互动倾向，不据单一十神判断婚姻次数、对象吉凶或必然结果。",
        },
        {
            "id": "turning-points", "title": "人生转折：变化通常从哪里开始", "listTitle": "变化来到时先核对什么",
            "core": f"在{primary_theme}与{supporting_theme}重新分配时推动身份更新", "behavior": "先感到旧办法不够用，再逐步调整角色、关系或生活安排",
            "tension": f"把短期不适误认为必须立刻推翻一切，或因{dominant_profile['risk']}迟迟不动",
            "evidence": f"大运背景、合冲结构与已知事件共同形成时间线；{event_line}",
            "advice": "把变化拆成三个月可回看的实验，同时记录身体、关系和现金流的代价", "counter": "具体事件仍受时代、家庭和个人选择影响，流年线索不能写成必然发生",
            "meaning": "人生转弯前经常先出现旧身份已经无法承接新需要的感觉",
            "settings": ["原本稳定的安排突然不再合身", "机会与压力在同一时间到来", "一次搬迁或岗位变化改变了生活半径", "关系中的角色需要重新协商", "过去擅长的方法开始失效", "心里反复出现想换一种活法的念头"],
            "actions": ["确认新责任是否带来相应权限和资源。", "区分这次选择是在逃离情绪，还是靠近长期目标。", "三个月后复盘身心、关系和现金流。", current_luck, f"已知经历线索：{event_line}"],
            "boundary": "大运提供十年背景，不把某一年写成必然事件；用户经历只用于复核，不用于事后凑解释。",
        },
        {
            "id": "wellbeing", "title": "身心节律：什么时候最需要照顾自己", "listTitle": "适合长期坚持的恢复安排",
            "core": f"让{profile['restore']}成为稳定恢复入口", "behavior": "先完成责任，稍后才处理自己的疲惫和情绪",
            "tension": f"长期处在“{dominant_profile['risk']}”的高负荷状态", "evidence": f"{climate_text}的时令偏性与{strongest}较显的生活节奏",
            "advice": "记录睡眠、情绪、活动量和工作负荷，让身体信号比解释更早进入决策", "counter": "任何持续不适都应先接受正规医学评估，不能用五行象意替代诊断",
            "meaning": "身体不是完成目标之后才需要照顾的部分，而是所有目标能够持续的前提",
            "settings": ["连续几周都在赶进度", "晚上停下后头脑仍无法安静", "对小事的耐心明显下降", "休息了一天却仍觉得没有恢复", "照顾别人时总把自己排在最后", "明知疲惫仍不愿取消安排"],
            "actions": [f"恢复入口：{profile['restore']}。", "连续四周记录睡眠、情绪、运动和负荷。", "把休息写进日程，不等待所有事情做完。", "持续或明显不适时及时接受正规检查。", "每天设置一个明确的工作结束信号。"],
            "boundary": "传统五行只用于讨论生活节律，不对应具体疾病，也不构成诊断或治疗建议。",
        },
        {
            "id": "review", "title": "哪些地方最值得继续验证", "listTitle": "下一轮复核的线索",
            "core": f"把确定结构、条件判断和待验证部分分开", "behavior": "用有明确年月的经历检查报告，而不是只接受听起来顺耳的描述",
            "tension": "为了得到确定感，把含糊信息也解释成已经命中", "evidence": f"当前资料等级为{quality['level']}，已记录{quality['eventCount']}项事件",
            "advice": "优先补充能够推翻判断的反例，并保留每次版本变化", "counter": "若现实长期不符合，应降低规则权重或直接撤回结论",
            "meaning": "诚实的研判不怕留下空白，也允许后来发生的真实生活修正今天的解释",
            "settings": ["回看一段已经走完的人生阶段", "家人对出生时刻有不同记忆", "某条描述听起来很准却找不到具体例子", "一次重大事件与预测完全不符", "想继续追问更具体的年份", "补充了新的出生凭证或人生经历"],
            "actions": (quality["reasonText"] or ["现有资料达到当前模型最高等级，继续记录新事件用于滚动复核。"]) + ["记录最符合与最不符合报告的各一个例子。", "补充事件时写清年月、类型和实际结果。", f"当前事件概览：{event_context}"],
            "boundary": "系统不会因资料缺失而自动编造时辰，也不会把后来发生的事改写成事前已经预测。",
        },
        {
            "id": "actions", "title": f"{stage_name}：未来十二个月怎样落到行动", "listTitle": "接下来可以真正执行的约定",
            "core": f"围绕{stage_focus}形成少而稳定的改变", "behavior": f"把{profile['strength']}投入一件能留下长期结果的事情",
            "tension": f"同时启动太多改变，最后重新回到{profile['risk']}", "evidence": f"当前年龄阶段、{family}动力与大运背景共同限定行动重点",
            "advice": "每三个月只复盘目标、关系、现金流和身心四张表，不用每天推翻方向", "counter": "行动效果必须由现实结果验证，命盘不能保证成功",
            "meaning": "所谓转运更多发生在选择方式改变之后，而不是等待外界突然给出答案",
            "settings": ["准备给新一年定目标", "旧计划执行到一半开始动摇", "工作和家庭同时需要投入", "想培养一项真正能留下来的能力", "发现生活被琐事切得很碎", "需要为下一阶段重新分配时间"],
            "actions": [f"事业：围绕“{profile['work']}”连续投入十二个月。", f"身心：用“{profile['restore']}”建立固定恢复仪式。", "财务：重大决定隔夜，并核对最坏结果。", "关系：重要感受在累积成旧账前说出来。", "复盘：每季度记录一次重要选择和真实结果。"],
            "boundary": "这些建议坚持低风险、可执行和可复盘，不构成保证结果的开运承诺。",
        },
    ]

    context_by_id = {context["id"]: context for context in contexts}
    family_priority = {
        "自主驱动": ["career", "relationships"],
        "表达创造": ["career", "character"],
        "资源经营": ["wealth", "career"],
        "规则责任": ["career", "structure"],
        "学习内化": ["structure", "character"],
        "综合承接": ["character", "career"],
    }[family]
    stage_priority = {
        "成长奠基期": ["character", "wellbeing", "relationships"],
        "身份探索期": ["character", "career", "relationships"],
        "立业展开期": ["career", "relationships", "wealth"],
        "结构重整期": ["career", "wealth", "wellbeing"],
        "经验回收期": ["wellbeing", "wealth", "relationships"],
    }[stage_name]
    event_priority_map = {
        "事业": "career", "教育": "character", "财务": "wealth", "关系": "relationships",
        "子女": "relationships", "迁移": "turning-points", "健康": "wellbeing", "亲属": "relationships",
    }
    event_priority = [event_priority_map[event["type"]] for event in data["events"] if event["type"] in event_priority_map]
    priority = []
    stage_head = stage_priority if stage_name == "成长奠基期" else stage_priority[:1]
    for section_id in [*event_priority[:2], *stage_head, family_priority[0]]:
        if section_id not in priority and section_id not in {"portrait", "actions"}:
            priority.append(section_id)
    remaining = [
        section_id for section_id in context_by_id
        if section_id not in {"portrait", "actions"} and section_id not in priority
    ]
    remaining.sort(key=lambda section_id: hashlib.sha256(f"{seed}|chapter-order|{section_id}".encode("utf-8")).hexdigest())
    chapter_order = ["portrait", *priority, *remaining, "actions"]

    sections = []
    for section_id in chapter_order:
        context = context_by_id[section_id]
        context = {
            **context,
            "name": data["name"],
            "stageName": stage_name,
            "stageFocus": stage_focus,
            "stageNarrative": stage_narrative,
            "chartNarrative": chart_narrative,
            "axisAttention": axes[0]["value"],
            "axisDecision": axes[1]["value"],
            "axisDrive": axes[2]["value"],
            "axisPace": axes[3]["value"],
        }
        scenes, voice = _compose_scenes(seed, context["id"], context)
        sections.append({
            "id": context["id"],
            "title": context["title"],
            "summary": _section_summary(seed, context["id"], context),
            "scenes": scenes,
            "listTitle": context["listTitle"],
            "items": [
                _individualize(item, seed, f"{context['id']}:item:{index}")
                for index, item in enumerate(_ordered_sample(seed, f"{context['id']}:actions", list(context["actions"]), min(4, len(context["actions"]))))
            ],
            "note": _section_note(seed, context["id"], context["boundary"]),
            "insight": _section_insight(seed, context["id"], context),
            "narrativeVoice": voice,
        })

    return {
        "seedVersion": "composite-narrative-v1",
        "lifeStage": {"name": stage_name, "focus": stage_focus},
        "axes": axes,
        "chapterOrder": chapter_order,
        "sections": sections,
    }


def narrative_text(report: dict[str, Any]) -> str:
    parts: list[str] = []
    for section in report.get("sections") or []:
        parts.extend([section.get("summary", ""), *(section.get("scenes") or []), section.get("insight", "")])
        parts.extend(section.get("items") or [])
    return re.sub(r"\s+", "", "".join(parts))


def narrative_similarity(report_a: dict[str, Any], report_b: dict[str, Any], width: int = 5) -> float:
    def shingles(text: str) -> set[str]:
        return {text[index:index + width] for index in range(max(0, len(text) - width + 1))}

    left = shingles(narrative_text(report_a))
    right = shingles(narrative_text(report_b))
    if not left and not right:
        return 1.0
    return len(left & right) / max(1, len(left | right))
