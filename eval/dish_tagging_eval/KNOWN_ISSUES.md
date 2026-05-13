# Golden Set Dual-Model 已知边界争议

记录 2026-05-12 Opus 4.7 + Codex GPT-5.4 共创跑完 171 条后, 发现的边界判定争议点。**当前决策原则: 先扩召回**(应用层视角, 双方说法都有道理时倾向更可能被召回的标签); 这些争议**暂不细究**, 等后续 V1 推荐链路跑出 user feedback 再迭代。

---

## P0 — 枚举边界 (1 条)

### d026 酸辣粉 `grain_type` 红薯粉归类
- **争议**: 红薯粉(酸辣粉用)是精制淀粉但非米粉, prompt 锚词列表无"红薯粉"
- **Opus 给**: `白米` (类推米粉, 高 GI 精制淀粉等价)
- **Codex 主张**: `其他` (但"其他"不在 grain_type 7 项枚举内, 无效)
- **现状**: 维持白米, `needs_review=true`
- **后续方向**:
  - 选项 A: 维持白米 (已在 v3 prompt patch 加显式锚点"红薯粉/绿豆粉/魔芋粉 → 白米")
  - 选项 B: 在 grain_type 枚举里加"其他淀粉"作为兜底值

---

## P1 — Codex 反驳后接受的修正 (10 条 codex_wins)

可能存在过度接受。**保留现状, 标记后续可重审**。

| dish | 字段 | 旧/Opus | 新/Codex(采纳) | 重审优先级 |
|---|---|---|---|---|
| d012 回锅肉 | sweet_sauce_level | 0 | **1** | 低 (传统含甜面酱事实) |
| d027 钵钵鸡 麻辣 | wetness | 1 | **2** | 中 (浸卤汁定义边界) |
| d029 酸豆角肉末 | main_ingredient_type | 纯素 | **红肉** | **高** (命名优先 vs 体积主体, 应用层影响召回) |
| d038 及第粥 | cuisine | 潮汕 | **粤菜** | **高** (违反 prompt "restaurant_category 优先"规则) |
| d039 艇仔粥 | cuisine | 潮汕 | **粤菜** | **高** (同上) |
| d040 生滚鱼片粥 | cuisine | 潮汕 | **粤菜** | **高** (同上) |
| d056 无锡酱排骨 | sweet_sauce_level | 3 | **2** | 低 (按字面锚词严格, 但无锡浓糖实际) |
| d060 拔丝山药 | cuisine | 江浙 | **鲁菜** | 中 (餐厅误导 vs 菜名归属) |
| d063 蜜汁烤翅 | wetness | 1 | **2** | 低 (一致性: 对齐 d047 蜜汁叉烧) |
| d169 麻辣香锅 | processed_meat_flag | true | **false** | 中 (菜单未明示保守原则) |

**最值得后续重审的 4 条**: d029 / d038 / d039 / d040
- 这 4 条都涉及"prompt 字面规则 vs 实际语义"的冲突
- d029 命名 vs 体积主体优先级未在 v3 prompt 明示
- d038-d040 菜系归属优先 restaurant_category 还是菜名实质, prompt 规则不够明确

---

## P2 — Opus 维持决策但 Codex 反驳 (5 条 opus_wins)

可能 Codex 是对的。保留现状, 标记后续可重审。

| dish | 字段 | Opus(维持) | Codex 主张 | 我的理由 | 重审优先级 |
|---|---|---|---|---|---|
| d109 酸菜鱼套餐 含饭 | wetness | 3 | 2 | 酸菜鱼本体=汤鱼 inherent | 低 |
| d135 拍黄瓜 | cuisine/oil/spicy | 川菜/3/1 | 通用/2/0 | restaurant=蜀香源(川菜店) | 中 |
| d140 烤鸡翅 3只 | cuisine/sweet | 韩式/2 | 中式/0 | restaurant_category=韩式 | 中 |
| d160 腊肠煲仔饭 | cooking_method | 煮 | 蒸/焗 | prompt 无"焗"枚举 | **高** (prompt 锚点缺失) |
| d145 柠檬水(赠品) | cooking_method | 生 | 凉拌 | 饮品=生 vs 非食物兜底 | 低 |

**最值得后续 prompt 改进的**: d160 煲仔饭 cooking_method
- prompt 9 项 cooking_method (蒸/煮/烤/炒/炖/油炸/凉拌/生/煎) 不包含"焗"
- 煲仔饭/盐焗鸡的"焗"工艺当前 fallback 到"煮/烤", 长期建议加"焗"枚举

---

## V3 Prompt 待评估的潜在改进

基于 dual-model 跑 171 条沉淀:

1. **新增 cooking_method "焗"** (针对煲仔饭/盐焗鸡 d160/d150 边界)
2. **新增 cooking_method "卤"** (针对 d037 豉油鸡腿 / 卤味边界, 当前 fallback "煮")
3. **明确 cuisine 优先级规则**: restaurant_category 是 hint 还是 hard rule? d038-d040 / d060 / d135 都涉及"餐厅类目误导 vs 菜名实质"
4. **明确 main_ingredient_type 命名 vs 体积主体优先级** (d029 酸豆角肉末争议)
5. **grain_type 枚举增加"其他淀粉"或显式锚点扩展** (d026 红薯粉)

---

## 重审触发条件

下列任一情形发生时, 重新审视本文档争议条目:
- V1 推荐链路上线后, 用户 feedback 反映某个 dish 分类不准
- 跑 score.py 发现某个模型在边界 case 上准确率显著偏低
- v3 prompt 后续迭代到 v4 (主动触发重审)
- 累积有 ≥10 个新边界 case 出现, 触发 prompt 系统性升级

---

## 信息沉淀路径

- 完整规则参考: `eval/dish_tagging_eval/CRITICAL_RULES.md`
- V3 prompt patched: `prompts/tag_dishes_v3_draft.md` (eval 下)
- 双模型 audit 链路与进度状态: 2026-05-13 清理 (流程已完结, 历史见 git log commit 5727b21)
- V3 prompt 原版: 历史在 git (commit 5727b21 之前)
