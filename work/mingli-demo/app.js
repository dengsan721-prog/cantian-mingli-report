const GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"];
const ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"];

const seedRecords = [
  {
    name: "张乖平",
    gender: "male",
    calendarType: "lunar",
    year: 1965,
    month: 10,
    day: 29,
    timeText: "",
    birthplace: "陕西省宝鸡市陈仓区周原镇营子头村15组",
    chart: {
      solarDate: "1965-11-21",
      bazi: "乙巳年、丁亥月、己卯日",
      dayMaster: "己土",
      confidence: "C",
      model: "寒土逢水、杀印相生、巳亥冲动、责任成局型",
      notes: "无时辰版；农历按非闰月处理。"
    }
  },
  {
    name: "邓秀龙",
    gender: "male",
    calendarType: "lunar",
    year: 1962,
    month: 9,
    day: 14,
    timeText: "早上9点",
    birthplace: "陕西省商洛市山阳县中村镇",
    chart: {
      solarDate: "1962-10-12",
      bazi: "壬寅年、庚戌月、癸未日；北京时间早9点为丁巳时，真太阳时可能仍在辰时尾段",
      dayMaster: "癸水",
      confidence: "B",
      model: "癸水承压、官印相生、财官并临、晚年再起型",
      notes: "早上9点处于辰巳边界，需要校时。"
    }
  },
  {
    name: "邓焱",
    gender: "male",
    calendarType: "lunar",
    year: 1991,
    month: 4,
    day: 9,
    timeText: "子时",
    birthplace: "陕西省山阳县西照川镇碾子坪村石佛寺乡碾子坪村湾子组",
    chart: {
      solarDate: "1991-05-22",
      bazi: "辛未年、癸巳月、壬辰日；子时需早子夜子和真太阳时校验",
      dayMaster: "壬水",
      confidence: "B",
      model: "壬水受火型、财旺压身型、流动成事型",
      notes: "子时边界需细校。"
    }
  },
  {
    name: "马雨芬",
    gender: "female",
    calendarType: "lunar",
    year: 1988,
    month: 10,
    day: 21,
    timeText: "",
    birthplace: "陕西省宝鸡市陈仓区周原镇王家村马家沟组",
    chart: {
      solarDate: "1988-11-29",
      bazi: "戊辰年、癸亥月、戊子日",
      dayMaster: "戊土",
      confidence: "C",
      model: "财重现实型、内压承载型、家庭稳定型",
      notes: "无时辰版。"
    }
  }
];

const form = document.getElementById("birthForm");
const output = document.getElementById("reportOutput");
const title = document.getElementById("reportTitle");
const confidenceBadge = document.getElementById("confidenceBadge");

function normalizeText(value) {
  return String(value || "").replace(/\s+/g, "").trim();
}

function getFormData() {
  return {
    name: document.getElementById("name").value.trim() || "某某",
    gender: document.getElementById("gender").value,
    calendarType: document.getElementById("calendarType").value,
    year: Number(document.getElementById("year").value),
    month: Number(document.getElementById("month").value),
    day: Number(document.getElementById("day").value),
    isLeapMonth: document.getElementById("isLeapMonth").checked,
    timeText: document.getElementById("timeText").value.trim(),
    birthplace: document.getElementById("birthplace").value.trim()
  };
}

function findSeed(data) {
  return seedRecords.find((item) => {
    return normalizeText(item.name) === normalizeText(data.name)
      && item.year === data.year
      && item.month === data.month
      && item.day === data.day
      && item.calendarType === data.calendarType;
  });
}

function sexagenaryYear(year) {
  const index = (year - 4) % 60;
  const fixed = index < 0 ? index + 60 : index;
  return `${GAN[fixed % 10]}${ZHI[fixed % 12]}`;
}

function jdn(year, month, day) {
  const a = Math.floor((14 - month) / 12);
  const y = year + 4800 - a;
  const m = month + 12 * a - 3;
  return day + Math.floor((153 * m + 2) / 5) + 365 * y + Math.floor(y / 4) - Math.floor(y / 100) + Math.floor(y / 400) - 32045;
}

function sexagenaryDay(year, month, day) {
  const index = (jdn(year, month, day) + 49) % 60;
  return `${GAN[index % 10]}${ZHI[index % 12]}`;
}

function inferHourBranch(text) {
  const raw = normalizeText(text);
  if (!raw || raw.includes("未知") || raw.includes("不详")) return null;
  const direct = ZHI.find((branch) => raw.includes(`${branch}时`) || raw === branch);
  if (direct) return direct;
  const match = raw.match(/(\d{1,2})(?::\d{1,2})?/);
  if (!match) return null;
  const hour = Number(match[1]);
  if (hour >= 23 || hour < 1) return "子";
  if (hour < 3) return "丑";
  if (hour < 5) return "寅";
  if (hour < 7) return "卯";
  if (hour < 9) return "辰";
  if (hour < 11) return "巳";
  if (hour < 13) return "午";
  if (hour < 15) return "未";
  if (hour < 17) return "申";
  if (hour < 19) return "酉";
  if (hour < 21) return "戌";
  return "亥";
}

function seasonProfile(month, calendarType) {
  const seasonMonth = Number(month);
  const profiles = {
    spring: {
      name: "春木生发",
      climate: "木气渐旺，重在疏达与成形",
      useful: "宜有火来发用，土来承载，金来成规",
      risk: "木旺则急，容易责任、规矩、人情牵动"
    },
    summer: {
      name: "夏火炎上",
      climate: "火气旺，重在降燥、守水、稳节奏",
      useful: "宜金水调候，土要有度",
      risk: "火过则急，财务、情绪、睡眠容易受压"
    },
    autumn: {
      name: "秋金收敛",
      climate: "金气成形，重在规则、技术、判断",
      useful: "宜火暖、木通、水润",
      risk: "金重则硬，沟通容易偏直"
    },
    winter: {
      name: "冬水寒凝",
      climate: "水寒渐盛，重在火暖、土定、木疏",
      useful: "宜火土立局，金水不可过寒",
      risk: "寒湿过重则操心、迟滞、身体沉重"
    }
  };
  const m = seasonMonth;
  if (calendarType === "lunar") {
    if ([1, 2, 3].includes(m)) return profiles.spring;
    if ([4, 5, 6].includes(m)) return profiles.summer;
    if ([7, 8, 9].includes(m)) return profiles.autumn;
    return profiles.winter;
  }
  if ([3, 4, 5].includes(m)) return profiles.spring;
  if ([6, 7, 8].includes(m)) return profiles.summer;
  if ([9, 10, 11].includes(m)) return profiles.autumn;
  return profiles.winter;
}

function buildChart(data) {
  const seed = findSeed(data);
  if (seed) return { ...seed.chart, source: "seed" };

  const yearPillar = sexagenaryYear(data.year);
  const canEstimateDay = data.calendarType === "solar" && data.year && data.month && data.day;
  const dayPillar = canEstimateDay ? sexagenaryDay(data.year, data.month, data.day) : "待精排";
  const dayMaster = canEstimateDay ? `${dayPillar[0]}${stemElement(dayPillar[0])}` : "待精排";
  const hourBranch = inferHourBranch(data.timeText);
  const timeNote = hourBranch ? `${hourBranch}时，需结合出生地校验真太阳时` : "时辰不详，子女、晚年与应期降级";

  return {
    solarDate: data.calendarType === "solar" ? `${data.year}-${pad(data.month)}-${pad(data.day)}` : "农历输入，前端 demo 未做精确阳历换算",
    bazi: `${yearPillar}年、月柱待节气精排、${dayPillar}日、${hourBranch ? `${hourBranch}时待定` : "时柱不详"}`,
    dayMaster,
    confidence: data.calendarType === "solar" && hourBranch ? "B" : "C",
    model: `${seasonProfile(data.month, data.calendarType).name}、资料校验型、待精排补强型`,
    notes: timeNote,
    source: "generated"
  };
}

function stemElement(stem) {
  const map = {
    甲: "木", 乙: "木", 丙: "火", 丁: "火", 戊: "土",
    己: "土", 庚: "金", 辛: "金", 壬: "水", 癸: "水"
  };
  return map[stem] || "";
}

function pad(value) {
  return String(value).padStart(2, "0");
}

function genderText(value) {
  if (value === "male") return "男";
  if (value === "female") return "女";
  return "未知";
}

function calendarText(value) {
  return value === "solar" ? "阳历" : "农历";
}

function confidenceText(level) {
  const map = {
    A: "A级：资料完整，边界风险低",
    B: "B级：资料较完整，存在时辰或真太阳时边界",
    C: "C级：缺少时辰或精排条件，主结构可断，细节降级",
    D: "D级：日期、历法或性别存在疑点，仅作初判"
  };
  return map[level] || map.C;
}

function list(items) {
  return `<ul>${items.map((item) => `<li>${item}</li>`).join("")}</ul>`;
}

function meta(label, value) {
  return `<div class="meta-item"><b>${label}</b><span>${value || "待补"}</span></div>`;
}

function buildReport(data) {
  const chart = buildChart(data);
  const season = seasonProfile(data.month, data.calendarType);
  const isSeed = chart.source === "seed";
  const hasHour = Boolean(inferHourBranch(data.timeText) || (isSeed && data.timeText));

  title.textContent = `${data.name}命理报告`;
  confidenceBadge.textContent = `${chart.confidence}级`;

  const hourRisk = hasHour
    ? "时辰已录入，但仍需根据出生地经度校验真太阳时；若靠近交界，时柱相关判断保持弹性。"
    : "时辰未明，子女、晚年、隐性性格、健康细节与具体应期全部降级。";

  const seedNote = isSeed
    ? "本档命中内置资料库，优先采用已校验盘面。"
    : "本档为新录入资料，当前生成模型版报告；生产版需接入后端排盘服务完成农历换算、节气和四柱精排。";

  return `
    <h3>一、基础资料与排盘校验</h3>
    <div class="meta-grid">
      ${meta("姓名", data.name)}
      ${meta("性别", genderText(data.gender))}
      ${meta("出生", `${calendarText(data.calendarType)} ${data.year}年${data.month}月${data.day}日${data.isLeapMonth ? " 闰月" : ""}`)}
      ${meta("时辰", data.timeText || "未提供")}
      ${meta("出生地", data.birthplace)}
      ${meta("盘面", chart.bazi)}
      ${meta("日主", chart.dayMaster)}
      ${meta("模型", chart.model)}
    </div>
    <p class="note">${seedNote}${chart.notes ? ` ${chart.notes}` : ""} ${confidenceText(chart.confidence)}。</p>

    <h3>二、命局总象</h3>
    <p>${data.name}这一档的总象以“${chart.model}”为主。命局研判先看出生季节与日主承受力，再看财官印食之间的流通。此类报告不把单点神煞当作结论，而是从月令、气候、十神、现实角色和大运阶段一起判断。</p>
    <p>从当前资料看，盘面重点在“${season.name}”。${season.climate}。若后续补入精确时辰和人生事件，报告可以进一步校正用忌、事业节点、家庭应事与健康象意。</p>

    <h3>三、五行气势</h3>
    ${list([
      `木：主生发、规矩、压力与表达通道。当前季节模型提示：${season.name.includes("春") ? "木气较显，宜疏不宜郁。" : "木作为后天疏通力，需要结合日主再定强弱。"}`,
      `火：主温度、精神、印星或财星作用。${season.useful}`,
      "土：主承载、家庭、现实责任与资产根基。报告中必须判断土是护身还是压身。",
      "金：主规则、技术、工具、账目与表达边界。生产版会结合天干地支藏干细分。",
      "水：主流动、财源、信息、人脉与情绪系统。水旺要防寒湿，水弱要防消耗。"
    ])}

    <h3>四、十神与格局层</h3>
    <p>当前 demo 以模型库进行初判：财星代表现实资源，官杀代表压力与规矩，印星代表保护与经验，食伤代表表达和技术输出，比劫代表自我与同辈竞争。生产版会根据完整四柱自动拆解十神、藏干、刑冲合害，并判断成格、破格与救应。</p>
    <p>本档最需要补强的不是文字，而是校验：节气月柱、真太阳时、早子夜子、大运起运和真实人生事件。只有这些补上，格局层次才能从“模型判断”上升到“专业精断”。</p>

    <h3>五、性格结构</h3>
    <p>${data.name}的性格研判以日主、季节气候与十神压力共同判断。${season.risk}。若盘中财官较重，现实责任感会强，容易把家庭、钱财、规矩和人情放在心上；若印星有力，则遇事更重经验、原则和长期稳定。</p>
    <p>这类模型强调一个核心：性格不是简单标签，而是人在环境压力下形成的处理方式。报告会同时写优点、短板和可修正路径。</p>

    <h3>六、事业与财务模型</h3>
    ${list([
      "事业上优先判断成事方式：技术立身、资源整合、经营承载、管理规则或流动见财。",
      "财务上区分来财与守财：能接触资源不等于能守住资源，合伙、借贷、担保和家族账目必须单独判断。",
      "若命局寒湿，宜火土立局，适合稳定经营与长期信用；若命局燥烈，宜金水调候，适合规则、技术、现金流管理。",
      "行动建议必须落到主业、账目、边界、合作、资产安排，不只写泛泛的注意事项。"
    ])}

    <h3>七、家庭关系与六亲</h3>
    <p>家庭部分会分父母祖上、伴侣关系、子女后辈和家族责任四层。${hourRisk}</p>
    <p>无论命局强弱，家庭判断都要把“承担方式”和“沟通方式”分开：有些人承担很多，但表达偏硬；有些人情感深，但不擅长说。报告会把这些现实落点写清楚。</p>

    <h3>八、健康象意</h3>
    <p>健康部分只作传统命理象意参考，不替代医学判断。报告会关注寒暖燥湿、睡眠、脾胃、情绪压力、筋骨水液代谢等生活系统，并给出节奏调整，不作疾病定论。</p>

    <h3>九、大运与阶段走势</h3>
    <p>生产版会根据性别、年干阴阳、节气距离计算起运，并逐步输出每步大运的机会、风险、冲合与置信度。当前 demo 对新档只输出结构提示；命中内置资料库的人，可继续扩展为完整大运时间轴。</p>

    <h3>十、专家质询</h3>
    ${list([
      data.calendarType === "lunar" ? "农历生日需确认是否闰月；当前按表单状态记录。" : "阳历生日已记录，仍需核对是否靠近节气交界。",
      "出生地需要用于真太阳时校正，尤其陕西、香港等地不应忽略经度差。",
      hasHour ? "时辰相关判断需检查是否靠边界。" : "无时辰导致子女、晚年、应期和部分健康细节降级。",
      "建议补充真实事件：结婚、生子、迁移、事业转折、破财、疾病、亲人变故等，用于反推喜忌。"
    ])}

    <h3>十一、行动方案</h3>
    ${list([
      "事业：先定主业轴线，再围绕技术、渠道、信用和规则积累。",
      "财务：建立家庭账、项目账、人情账，大额支出和合伙必须留边界。",
      "家庭：重大安排提前说清，避免用沉默或情绪代替规则。",
      "健康：按命局偏性调节寒暖燥湿，先稳睡眠、饮食、运动和情绪。",
      "校验：下一步补出生时刻、闰月确认、关键年份事件，即可升级为精修版。"
    ])}

    <h3>十二、最终断语</h3>
    <p>${data.name}这份报告的当前定位，是“资料入库后的系统研判版”。它已经能生成完整结构、指出核心倾向、给出行动方案；但真正的最高规格，还要继续补齐精排和人生事件校验。命理报告的价值不在于说满，而在于把确定的说准，把不确定的标清，把能改变的落到行动上。</p>
  `;
}

function render() {
  const data = getFormData();
  output.innerHTML = buildReport(data);
}

document.getElementById("loadSeedButton").addEventListener("click", () => {
  const sample = seedRecords[(Math.floor(Date.now() / 1000)) % seedRecords.length];
  document.getElementById("name").value = sample.name;
  document.getElementById("gender").value = sample.gender;
  document.getElementById("calendarType").value = sample.calendarType;
  document.getElementById("year").value = sample.year;
  document.getElementById("month").value = sample.month;
  document.getElementById("day").value = sample.day;
  document.getElementById("isLeapMonth").checked = false;
  document.getElementById("timeText").value = sample.timeText;
  document.getElementById("birthplace").value = sample.birthplace;
  render();
});

document.getElementById("printButton").addEventListener("click", () => window.print());

form.addEventListener("submit", (event) => {
  event.preventDefault();
  render();
});

render();

