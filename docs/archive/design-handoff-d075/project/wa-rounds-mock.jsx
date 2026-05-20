// wa-rounds-mock.jsx — 4 per-round datasets for L1/L2/L3/Final panels.
// Swapped into window.MOCK before each render so panels naturally pick up the
// right round's numbers without changing panel internals.

(function () {
  function deepClone(o) { return JSON.parse(JSON.stringify(o)); }
  const baseL1     = window.MOCK.L1;
  const baseCombos = window.MOCK.L2_COMBOS;
  const baseKPI    = window.MOCK.L2_KPI;
  const baseL3     = window.MOCK.L3;
  const baseFinal  = window.MOCK.FINAL;

  // ─── R1 ───────────────────────────────────────────
  // identical to the existing single mock — that IS R1
  const R1 = {
    L1: deepClone(baseL1),
    L2_COMBOS: deepClone(baseCombos),
    L2_KPI: deepClone(baseKPI),
    L3: deepClone(baseL3),
    FINAL: deepClone(baseFinal),
  };

  // helper: rotate top of L2_COMBOS so a different combo is rank 1
  function liftToTop(combos, restName) {
    const i = combos.findIndex(c => c.restaurant === restName);
    if (i < 0) return combos;
    const c = combos[i];
    combos.splice(i, 1);
    combos.unshift({ ...c, total_score: c.total_score + 0.2 });
    combos.forEach((c, j) => (c.rank = j + 1));
    return combos;
  }
  function dropMatching(combos, predicate, count) {
    let removed = 0;
    return combos.filter(c => {
      if (removed >= count) return true;
      if (predicate(c)) { removed++; return false; }
      return true;
    });
  }

  // ─── R2 · "换一组" — novelty reshuffles top of L2 ─
  const R2 = (() => {
    const L1 = deepClone(baseL1);
    // ban: + 新增 "近 7 天 top1 已采纳" ban
    L1.restaurant_bans = [
      { rest: "椰客椰子鸡 (科兴店)", reason: "novelty 排除", detail: "R1 已采纳 + 24h 内 cooldown", count: 1 },
      ...baseL1.restaurant_bans.slice(0, 5),
    ];
    L1.ban_reason_agg = [
      { reason: "novelty cooldown (R1 已采纳)", count: 1 },
      { reason: "ETA 超限 (>45min)", count: 47 },
      { reason: "近 7 天吃过", count: 24 },
      { reason: "avoid_restaurants 命中", count: 18 },
      { reason: "价格异常 / 缺品类", count: 14 },
    ];
    L1.top_restaurants = baseL1.top_restaurants.slice().reverse().slice(0, 20);
    L1.funnel = deepClone(baseL1.funnel);
    L1.funnel.forEach(s => { if (s.kind === "combo") s.value = Math.round(s.value * 1.02); });

    const L2_COMBOS = liftToTop(deepClone(baseCombos), "汤先生 (后海店)");

    const L2_KPI = { ...baseKPI,
      score_min: L2_COMBOS[L2_COMBOS.length - 1].total_score.toFixed(3),
      score_max: L2_COMBOS[0].total_score.toFixed(3),
      restaurants_before_cap: 78, restaurants_after_cap: 33 };

    const L3 = deepClone(baseL3);
    L3.latency_ms = 2104;
    L3.input_tokens = 4912;
    L3.output_tokens = 588;
    L3.cache_read_input_tokens = 4124;
    L3.raw_response_blocks[0].text =
      `用户 R2 = "换一组"，触发 novelty 强约束：上一轮 top1 (椰客椰子鸡) 进入 24h cooldown。
- 新 top 候选：cmb_005 汤先生 (低脂合菜 + 杂粮饭，最近 14d 未吃) — 作 exploit #1
- cmb_002 Wagas 深圳湾店保留 (蛋白 60g) — exploit #2
- cmb_017 椰客椰子鸡【后海店】不同门店，未触发 cooldown — exploit #3 (替代被 cooldown 的科兴店)
- explore：cmb_028 新元素藜麦碗 (用户从未吃过) + cmb_034 真功夫海带排骨汤
约束 check：novelty cooldown ✓ / 同店 ≤ 1 ✓`;

    const FINAL = deepClone(baseFinal);
    FINAL[0] = { ...FINAL[0], rank: 1, kind: "exploit", combo_id: "cmb_005",
      restaurant: "汤先生 (后海店)", distance_km: 2.1, eta_min: 31, total_price: 52,
      score: 1.272, fit_score: 0.79,
      dishes: [{ name: "番茄牛尾汤套餐", price: 38 }, { name: "杂粮饭", price: 14 }],
      reason: "低脂合菜 + 杂粮饭，每份 30g 蛋白；R1 椰客刚吃过，换一家。" };
    FINAL[1] = { ...FINAL[1], rank: 2, kind: "exploit", combo_id: "cmb_017",
      restaurant: "椰客椰子鸡 (后海店)", distance_km: 2.4, eta_min: 28, total_price: 88,
      score: 1.162, fit_score: 0.77,
      dishes: [{ name: "椰子鸡汤锅 (单人)", price: 68 }, { name: "凉拌秋葵", price: 20 }],
      reason: "同样的椰子汤底，换后海店，避开 24h cooldown。" };
    FINAL[2] = { ...FINAL[2], rank: 3, restaurant: "Wagas (深圳湾店)" };
    FINAL[3] = { ...FINAL[3], rank: 4, kind: "explore", combo_id: "cmb_028",
      restaurant: "新元素 (科技园店)", distance_km: 1.1, eta_min: 23, total_price: 62,
      score: 1.014, fit_score: 0.71,
      dishes: [{ name: "藜麦牛腩碗", price: 48 }, { name: "罗勒鸡汤", price: 14 }],
      reason: "藜麦杂粮 + 罗勒鸡汤，从未吃过的轻食。" };
    FINAL[4] = { ...FINAL[4], rank: 5, restaurant: "真功夫 (科兴店)" };

    return { L1, L2_COMBOS, L2_KPI, L3, FINAL };
  })();

  // ─── R3 · "想喝汤，别给我面食和米饭" ───────────
  const R3 = (() => {
    const L1 = deepClone(baseL1);
    // -27 combos due to grain penalties
    L1.funnel = deepClone(baseL1.funnel);
    L1.funnel[1].value = 4128;  L1.funnel[1].dropped = 6995;
    L1.funnel[2].value = 2702;  L1.funnel[2].dropped = 1426;
    L1.funnel[4].value = 1741;
    L1.funnel[5].value = 1180;  L1.funnel[5].dropped = 561;
    L1.funnel[6].value = 1180;

    L1.dish_drops = [
      { reason: "grain_type = noodle (refine penalty)",     count: 412, layer: "hard" },
      { reason: "grain_type = rice (refine penalty)",       count: 318, layer: "hard" },
      { reason: "restaurant = 西少爷 (用户点名拒绝)",         count: 18,  layer: "hard" },
      { reason: "price > budget (单菜 > ¥45)",              count: 2148, layer: "hard" },
      { reason: "oil_level = high (规则: 减脂)",              count: 1937, layer: "hard" },
      { reason: "main_ingredient_type = 加工肉 (avoid)",    count: 1024, layer: "hard" },
      { reason: "wetness = dry & 已是干 (多样性)",            count: 728,  layer: "diversity" },
      { reason: "combo 总价 > ¥80 (上限)",                   count: 561,  layer: "price" },
    ];
    L1.restaurant_bans = [
      { rest: "西少爷肉夹馍 (深圳湾店)", reason: "用户点名拒绝", detail: "refine: '西少爷那个不要了'", count: 1 },
      { rest: "和府捞面 (科技园店)", reason: "全部 combo grain:noodle", detail: "all 14 combos penalty=-0.30", count: 14 },
      { rest: "霸蛮米粉 (后海店)", reason: "全部 combo grain:noodle", detail: "all 11 combos penalty=-0.30", count: 11 },
      ...baseL1.restaurant_bans.slice(0, 4),
    ];
    L1.ban_reason_agg = [
      { reason: "grain penalty (noodle / rice)", count: 730 },
      { reason: "ETA 超限 (>45min)", count: 47 },
      { reason: "近 7 天吃过", count: 23 },
      { reason: "avoid_restaurants 命中", count: 18 },
    ];
    L1.top_restaurants = [
      { name: "椰客椰子鸡 (科兴店)", combos: 22 },
      { name: "汤先生 (后海店)", combos: 19 },
      { name: "真功夫 (科兴店)", combos: 18 },
      { name: "云海肴 (深圳湾店)", combos: 17 },
      { name: "Element Fresh (深圳湾店)", combos: 14 },
      { name: "鸡公煲·小山 (科兴店)", combos: 13 },
      ...baseL1.top_restaurants.slice(6, 20),
    ];

    const L2_COMBOS = dropMatching(
      deepClone(baseCombos),
      c => /和府|霸蛮|西少爷|桂林米粉/.test(c.restaurant),
      6
    );
    L2_COMBOS.forEach((c, j) => (c.rank = j + 1));

    const L2_KPI = { ...baseKPI, restaurants_before_cap: 71, restaurants_after_cap: 28 };

    const L3 = deepClone(baseL3);
    L3.latency_ms = 2310;
    L3.raw_response_blocks[0].text =
      `用户 R3 = "想喝汤，别给我面食和米饭，西少爷那个不要了"。
- 强约束：grain:noodle / rice penalty -0.30 / -0.18；西少爷 -1.0
- soup 类 boost +0.22；wetness:wet +0.18
- 新 top 候选：cmb_001 椰客椰子鸡 重回 #1 (椰子汤底 + 无主食)
- cmb_034 真功夫海带排骨汤 + 杂粮饭 — 注：杂粮非面/非饭，符合
- cmb_017 椰客椰子鸡 (后海店) + 凉拌秋葵 — exploit #2
- explore：cmb_011 云海肴汽锅鸡 (云南汽锅 wet ✓) + cmb_038 蛙小侠酸菜鱼 (鱼 + 汤底)
约束 check：noodle/rice ✗ ✓ / 西少爷 ✗ ✓ / soup ✓ ✓`;

    const FINAL = deepClone(baseFinal);
    FINAL[0] = baseFinal[0];
    FINAL[1] = { ...baseFinal[2], rank: 2, restaurant: "汤先生 (后海店)" };
    FINAL[2] = { ...baseFinal[4], rank: 3, restaurant: "真功夫 (科兴店)" };
    FINAL[3] = { ...baseFinal[3], rank: 4, kind: "explore", combo_id: "cmb_011",
      restaurant: "云海肴 (深圳湾店)", distance_km: 0.7, eta_min: 21, total_price: 62,
      score: 1.024, fit_score: 0.73,
      dishes: [{ name: "汽锅鸡 (单人)", price: 48 }, { name: "云南酸菜豌豆汤", price: 14 }],
      reason: "云南汽锅鸡纯汤底，无主食搭配，符合无面无饭。" };
    FINAL[4] = { ...baseFinal[4], rank: 5, combo_id: "cmb_038",
      restaurant: "蛙小侠 (海岸城店)", distance_km: 1.9, eta_min: 27, total_price: 78,
      score: 0.962, fit_score: 0.68,
      dishes: [{ name: "酸菜美蛙鱼 (单人)", price: 58 }, { name: "凉拌木耳", price: 20 }],
      reason: "酸菜汤底 + 鱼 + 蛙肉高蛋白，wet + 无主食。" };

    return { L1, L2_COMBOS, L2_KPI, L3, FINAL };
  })();

  // ─── R4 · "别要重的，太油了" ───────────────────
  const R4 = (() => {
    const L1 = deepClone(baseL1);
    L1.funnel = deepClone(baseL1.funnel);
    L1.funnel[1].value = 3784;  L1.funnel[1].dropped = 7339;
    L1.funnel[2].value = 2486;  L1.funnel[2].dropped = 1298;
    L1.funnel[4].value = 1684;
    L1.funnel[5].value = 1142;  L1.funnel[5].dropped = 542;
    L1.funnel[6].value = 1142;

    L1.dish_drops = [
      { reason: "oil_level >= mid (refine: '别要重的')",   count: 1284, layer: "hard" },
      { reason: "cuisine = 川 / 湘 (refine penalty)",      count: 642,  layer: "hard" },
      { reason: "cook = 油炸 (refine avoid)",              count: 384,  layer: "hard" },
      { reason: "grain_type = noodle / rice (累计)",        count: 730,  layer: "hard" },
      { reason: "restaurant = 西少爷 (累计)",               count: 18,   layer: "hard" },
      { reason: "price > budget (单菜 > ¥45)",            count: 2148, layer: "hard" },
      { reason: "main_ingredient_type = 加工肉 (avoid)",   count: 1024, layer: "hard" },
      { reason: "combo 总价 > ¥80 (上限)",                  count: 542,  layer: "price" },
    ];
    L1.restaurant_bans = [
      { rest: "井格老灶火锅 (海岸城店)", reason: "全部 combo 重油重辣", detail: "all 12 combos oil=high", count: 12 },
      { rest: "太二酸菜鱼 (深圳湾店)", reason: "cuisine = 川 (refine)", detail: "all 9 combos cuisine penalty", count: 9 },
      { rest: "外婆家 (海岸城店)", reason: "≥3 道 mid+ oil", detail: "9/12 combos mid+", count: 9 },
      { rest: "西少爷肉夹馍 (深圳湾店)", reason: "累计点名拒绝", detail: "from R3", count: 1 },
      ...baseL1.restaurant_bans.slice(0, 3),
    ];
    L1.ban_reason_agg = [
      { reason: "重油 / 重辣 (refine)", count: 1668 },
      { reason: "grain penalty (累计)", count: 730 },
      { reason: "ETA 超限 (>45min)", count: 47 },
      { reason: "近 7 天吃过", count: 23 },
    ];
    L1.top_restaurants = [
      { name: "椰客椰子鸡 (科兴店)", combos: 22 },
      { name: "汤先生 (后海店)", combos: 19 },
      { name: "Element Fresh (深圳湾店)", combos: 18 },
      { name: "云海肴 (深圳湾店)", combos: 16 },
      { name: "新元素 (科技园店)", combos: 15 },
      { name: "Wagas (深圳湾店)", combos: 14 },
      ...baseL1.top_restaurants.slice(6, 20),
    ];

    const L2_COMBOS = dropMatching(
      deepClone(baseCombos),
      c => /井格|太二|外婆家|和府|霸蛮|西少爷/.test(c.restaurant),
      10
    );
    L2_COMBOS.forEach((c, j) => (c.rank = j + 1));

    const L2_KPI = { ...baseKPI, restaurants_before_cap: 62, restaurants_after_cap: 24 };

    const L3 = deepClone(baseL3);
    L3.latency_ms = 2208;
    L3.raw_response_blocks[0].text =
      `用户 R4 = "再来一轮，别要重的，太油了"。累计约束：
- soup + 无面/饭 (R3 继承)
- 新增：oil_level >= mid 全部 ban；川/湘菜系 ban；油炸 cook ban
- 候选都偏清淡：cmb_001 椰子鸡 (low oil) — exploit #1 不变
- cmb_011 云海肴汽锅鸡 — exploit #2 (清汤 + 蒸法)
- cmb_028 Element Fresh 三文鱼藜麦碗 — exploit #3 (生蒸 + low oil)
- explore：cmb_044 椰客凉拌系列 + cmb_007 新元素罗勒鸡汤碗
- 上一轮的 cmb_038 蛙小侠 (川味酸菜) 在此轮被剔除`;

    const FINAL = deepClone(baseFinal);
    FINAL[0] = baseFinal[0];
    FINAL[1] = { ...baseFinal[1], rank: 2, restaurant: "云海肴 (深圳湾店)",
      combo_id: "cmb_011", total_price: 62, fit_score: 0.78, score: 1.108,
      dishes: [{ name: "汽锅鸡 (单人)", price: 48 }, { name: "云南酸菜豌豆汤", price: 14 }],
      reason: "汽锅鸡清汤底，蒸法 0 油，符合 '别要重的'。" };
    FINAL[2] = { ...baseFinal[2], rank: 3, restaurant: "Element Fresh (深圳湾店)",
      combo_id: "cmb_028", total_price: 72, fit_score: 0.76, score: 1.052,
      dishes: [{ name: "盐蒸三文鱼藜麦碗", price: 58 }, { name: "罗勒鸡汤", price: 14 }],
      reason: "盐蒸三文鱼 + 藜麦，蛋白 38g，oil = none。" };
    FINAL[3] = { ...baseFinal[3], rank: 4, kind: "explore", combo_id: "cmb_044",
      restaurant: "椰客椰子鸡 (后海店)", distance_km: 2.4, eta_min: 28, total_price: 64,
      score: 0.984, fit_score: 0.71,
      dishes: [{ name: "凉拌牛展 (单人)", price: 48 }, { name: "椰子水", price: 16 }],
      reason: "凉拌冷食 + 椰水，最清的一组。" };
    FINAL[4] = { ...baseFinal[4], rank: 5, combo_id: "cmb_007",
      restaurant: "新元素 (科技园店)", distance_km: 1.1, eta_min: 23, total_price: 68,
      score: 0.942, fit_score: 0.69,
      dishes: [{ name: "罗勒鸡汤碗", price: 52 }, { name: "牛油果沙拉", price: 16 }],
      reason: "罗勒鸡清汤 + 牛油果，零中式重油。" };

    return { L1, L2_COMBOS, L2_KPI, L3, FINAL };
  })();

  window.WA_ROUNDS_DATA = { R1, R2, R3, R4 };
})();
