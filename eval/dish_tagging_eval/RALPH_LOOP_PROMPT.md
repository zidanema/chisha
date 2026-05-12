# Ralph-Loop Prompt: Dual-Model Golden Set Construction

## Goal
继续 Opus 4.7 + Codex GPT-5.4 共创 dish-tagging golden set。每次 iteration 跑 1 个 batch (5 条 dish),全部 35 batches 完成 → 输出 `<promise>GOLDEN_SET_COMPLETE</promise>` 退出。

## Workflow (严格按这个流程,每 iteration 做 1 次)

### Step 1: 检查状态
```bash
cd ~/chisha/eval/dish_tagging_eval/scripts && uv run python dual_pipeline.py status
```

- 如果 `is_complete: true` → 跑 `uv run python dual_pipeline.py merge`, 输出 `<promise>GOLDEN_SET_COMPLETE</promise>`, 完成
- 否则记下 `next_pending` 作为本 iteration 的 batch_idx

### Step 2: 取 batch input
```bash
cd ~/chisha/eval/dish_tagging_eval/scripts && uv run python dual_pipeline.py next-batch
```

得到 batch_idx + dishes (5 条 dish input, 含 raw_name/restaurant_name/restaurant_category_raw/category_raw/price/category_tag)。

### Step 3: Opus S1 草拟 (你 = Opus 4.7,担任本阶段)

读 `~/chisha/eval/dish_tagging_eval/CRITICAL_RULES.md` 一次(如果本 iteration 还没读过)。

对 5 条 dish,严格按 v3 prompt 规则 + CRITICAL_RULES.md 给 15 字段 expected:
- `dish_id` / `canonical_name` / `cuisine` / `main_ingredient_type` / `cooking_method`
- `oil_level` (1-5) / `protein_grams_estimate` (5g 粒度) / `vegetable_ratio_estimate` (0.0-1.0)
- `is_complete_meal` (bool) / `spicy_level` (0-3)
- `dish_role` ∈ {主菜,主食,配菜,汤,小食,饮品,套餐}
- `processed_meat_flag` (bool) / `sweet_sauce_level` (0-3)
- `wetness` (1-3) / `grain_type` ∈ {白米,糙米杂粮,精制面,全麦面,粗粮,粥,无}
- `tags` (list, 从 prompt 列表选 1-3 个)

每字段写一句 ≤30 字 rationale,仅在你认为可能争议或边界的字段写,简单 case 可省略。

落盘到 `data/_dual_audit/s1_batch_NNN.jsonl` (用 Write 工具, NNN 是 zero-padded 3 位 batch_idx)。

格式(一条 dish 一行 JSON):
```json
{"dish_id":"...","input":{...},"expected":{15 字段},"rationale":{字段: 一句话}}
```

### Step 4: Codex S2 对抗审查

用 `Agent(subagent_type="codex:codex-rescue", prompt=...)` 派任。Prompt 模板:

```
<task>
Adversarial review 5 dish-tagging records from Opus 4.7 (S1) for chisha eval batch NNN. Focus on 4 high-error fields (sweet_sauce_level / processed_meat_flag / dish_role / grain_type) plus any field marked uncertain in Opus rationale.

S1 records (one JSON object per line):

```jsonl
<把 5 条 S1 record inline 进来,每条只保留 input.raw_name + input.price + expected + rationale>
```
</task>

<grounding_rules>
v3 prompt 4 大易错字段:
- sweet_sauce_level: 烧/红/酱/糖/蜜/照/拔丝/京酱 → ≥2; 蜜/蜂蜜/拔丝/麦芽糖 → 3; 回锅肉/鱼香/宫保 → 1 (实际含糖但字面无锚)
- processed_meat_flag: 中式烧腊(叉烧/烧鸭, no 腊)=false; 腊肠/培根/午餐肉/蟹柳/鱼丸=true; 鲜内脏(肥肠/鸭血)=false; 麻辣香锅 default false (菜单未明示); 毛血旺 default true (固定含午餐肉)
- dish_role 优先级: 套餐>饮品>汤>主食>主菜>配菜>小食; 单点盖饭=主食(非套餐); 饺/包/汉堡/三明治=主食; 西式蛋白碗=主菜
- grain_type 枚举 7 值: 白米/糙米杂粮/精制面/全麦面/粗粮/粥/无 (不能写"其他"); 米粉/河粉/粿条/肠粉/红薯粉/绿豆粉=白米; 无谷物=无

6 边界判定:
- 西式蛋白碗(无谷物): is_complete_meal=true + grain=无 + role=主菜
- 套餐含汤(+汤/+老火靓汤): wetness=3
- 关东煮/卤味/钵钵鸡浸卤: wetness=2 (浸不喝)
- 非食物兜底(调料/餐具): spicy=0, role=小食, 全字段保守
- 中式烧腊: processed=false, cooking=烤, sweet=2
- 米制品/红薯粉: grain=白米

main_ingredient_type 命名 vs 体积:
- 菜名含蛋白源 (番茄牛腩饭/酸豆角肉末) → 蛋白源
- 菜名无蛋白源 (麻婆豆腐) → 体积主体
- 主食载体 (饺/粥) → 主食

LLM 幻觉防护:
- canonical_name 必须从 raw_name 派生
- 同名菜不同价 = 不同分量, protein 必须依赖 price
</grounding_rules>

<structured_output_contract>
Output a SINGLE markdown json code block with array of 5 objects:
{
  "dish_id": "...",
  "challenges": [
    {"field": "...", "opus_value": ..., "codex_value": ..., "verdict": "agree" | "disagree" | "uncertain", "reason": "≤50 字, 引用 v3 锚词"}
  ],
  "overall_assessment": "≤80 字"
}

强制 verdict 枚举: 只能用 "agree" / "disagree" / "uncertain". 不要用 "CONFIRM" / "CHALLENGE" / "BORDERLINE".
最少覆盖 4 高错字段. Output only json code block, no prose.
</structured_output_contract>
```

记下 Codex stdout 里的 challenges 列表(parse JSON code block)。

### Step 5: Opus S3 裁决 + 落 final

对每条 dish 做裁决:
- 所有字段 agree → consensus_status="agree"
- Codex disagree + Opus 接受 → consensus_status="codex_wins", disagreement_fields=[...], expected 改成 codex_value
- Codex disagree + Opus 维持 → consensus_status="opus_wins", disagreement_fields=[...], expected 保持
- Codex uncertain → 不算分歧,默认 Opus 维持,consensus_status="agree"
- 4 大字段任一 disagree 且 Opus 无强理由 → consensus_status="human_needed", needs_review=true

落盘到 `data/_dual_audit/final_batch_NNN.jsonl`,格式:
```json
{
  "dish_id": "...",
  "input": {...},
  "expected": {15 字段, S3 裁决后},
  "category_tag": "...",
  "anchor_notes": "≤40 字, 总结这条的关键判断",
  "needs_review": bool,
  "anchor_violations": [],
  "consensus_status": "agree" | "opus_wins" | "codex_wins" | "human_needed",
  "disagreement_fields": [...],
  "rationale": {
    "opus_s1_summary": "≤50 字",
    "opus_s3_rationale": "≤80 字, 裁决理由"
  }
}
```

### Step 6: Mark batch done
```bash
cd ~/chisha/eval/dish_tagging_eval/scripts && uv run python dual_pipeline.py mark-done <batch_idx>
```

如果返回 OK → iteration 结束 (本轮 stop, ralph-loop 会再次触发同一 prompt 跑下一 batch)。
如果返回 ERROR (schema/anchor 违规) → 修复 final_batch_NNN.jsonl 重新写,再 mark-done。

## 关键约束

1. **每 iteration 只跑 1 个 batch** (5 条 dish)。不要一次跑多个 batch 避免 context 爆炸。
2. **不要并行启动多个 Codex 子代理** (在 loop 里串行即可,简化错误处理)。
3. **必须读 CRITICAL_RULES.md 一次**, 然后内化规则跑 5 条。
4. **Codex stdout 解析失败 → 重试 1 次**,仍失败 → 把这条 batch 标 failed (`uv run python ... mark-done` 会失败,iteration 结束,下次还会重试同 batch)。
5. **每 iteration 必须落盘 s1_batch_NNN.jsonl + final_batch_NNN.jsonl 两个文件**。
6. **完成条件**: `dual_pipeline.py status` 返回 `is_complete: true` → 跑 merge → 输出完成 promise。

## 已完成进度 (Iteration 启动时初始状态)
- Batch 1-6 已完成 (d001-d030):
  - Batch 1/2: anchor seed (d001-d009 from ANCHOR_EXPECTED)
  - Batch 3-6: 川湘菜 d011-d030 dual-model 跑过
- Spike done (extra): d010, d155, d159, d162, d169
- 待跑: Batch 7-35 (29 batches × 5 dishes ≈ 145 dishes)

## 完成时输出
```
<promise>GOLDEN_SET_COMPLETE</promise>
```

附最终汇总信息(从 merge 输出抄):总 records 数, consensus 分布, needs_review 数。
