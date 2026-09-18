(() => {
  const categories = {
    palace: {
      name: "天宫云阙",
      sources: [
        "./assets/gallery/celestial-palace-01.png",
        "./assets/gallery/celestial-palace-02.png",
      ],
      alt: "云海之上的东方天宫与白玉天门",
      caption: "云阙高悬，像把眼前的纷繁重新放回更辽阔的秩序里。",
    },
    cosmos: {
      name: "星河命盘",
      sources: [
        "./assets/gallery/star-chart-01.png",
        "./assets/gallery/star-chart-02.png",
        "./assets/report-overview.png",
      ],
      alt: "星轨、日月与仙山构成的东方天穹",
      caption: "看见天时，不是等待答案降临，而是辨认自己正站在哪一种节律里。",
    },
    mountains: {
      name: "青绿仙山",
      sources: [
        "./assets/gallery/immortal-mountain-01.png",
        "./assets/gallery/immortal-mountain-02.png",
        "./assets/report-overview.png",
      ],
      alt: "金色能量水脉穿过青绿仙山与云海",
      caption: "山势有起伏，真正稳固的力量来自知道何时攀登、何时蓄势。",
    },
    elements: {
      name: "日月五行",
      sources: [
        "./assets/gallery/five-elements-01.png",
        "./assets/gallery/five-elements-02.png",
        "./assets/report-overview.png",
      ],
      alt: "日月与五种自然力量在云海中交汇",
      caption: "力量不必平均，重要的是让不同部分在恰当的时刻彼此成全。",
    },
    steps: {
      name: "神殿长阶",
      sources: [
        "./assets/gallery/divine-steps-01.png",
        "./assets/gallery/divine-steps-02.png",
        "./assets/report-path.png",
      ],
      alt: "穿越云门通向东方神殿的金色长阶",
      caption: "人生不是一跃而上，每一级台阶都在把选择变成真正属于你的路。",
    },
    pools: {
      name: "瑶池灵境",
      sources: [
        "./assets/gallery/jade-pool-01.png",
        "./assets/gallery/jade-pool-02.png",
        "./assets/report-relationships.png",
      ],
      alt: "瑶池、玉桥与天宫相连的明亮灵境",
      caption: "温柔并不削弱力量，能被安放的情绪，才会重新流动起来。",
    },
  };

  const positions = [
    "center center", "center 42%", "center 58%", "42% center", "58% center",
    "35% 45%", "65% 45%", "38% 60%", "62% 60%", "center 35%",
  ];
  const scales = [1, 1.025, 1.05, 1.075, 1.1];
  const saturations = [0.94, 1, 1.06, 1.12, 1.18];
  const brightness = [0.98, 1, 1.025, 1.05];
  const entries = [];

  Object.entries(categories).forEach(([category, config], categoryIndex) => {
    for (let index = 0; index < 50; index += 1) {
      entries.push({
        id: `${category}-${String(index + 1).padStart(3, "0")}`,
        category,
        categoryName: config.name,
        src: config.sources[(index + categoryIndex) % config.sources.length],
        position: positions[(index * 3 + categoryIndex) % positions.length],
        scale: scales[(index + categoryIndex * 2) % scales.length],
        saturation: saturations[(index * 2 + categoryIndex) % saturations.length],
        brightness: brightness[(index * 3 + categoryIndex) % brightness.length],
        alt: config.alt,
        caption: config.caption,
      });
    }
  });

  function hash(value) {
    let result = 2166136261;
    for (let index = 0; index < value.length; index += 1) {
      result ^= value.charCodeAt(index);
      result = Math.imul(result, 16777619);
    }
    return result >>> 0;
  }

  function pick(category, seed) {
    const candidates = entries.filter((entry) => entry.category === category);
    return candidates[hash(`${seed}:${category}`) % candidates.length];
  }

  function pickAny(categoryNames, seed) {
    const category = categoryNames[hash(`${seed}:category`) % categoryNames.length];
    return pick(category, seed);
  }

  globalThis.MingliImages = Object.freeze({
    categories: Object.freeze(categories),
    entries: Object.freeze(entries),
    pick,
    pickAny,
  });
})();
