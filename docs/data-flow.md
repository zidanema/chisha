# 数据流全景 · 周边外卖商家与菜品 (采集 → 推荐)

> 端到端地图: 从美团 App 屏幕一路到推荐输出, 跨两个 repo —— `~/waimai_data` (采集) + `~/chisha` (加工/打标/推荐)。
> 本文只画 **流程 + 产物 + 断裂点**。操作细节与 schema 交给单一权威:
> - 采集操作 / 风控旋钮 / 续传契约: `~/waimai_data/CLAUDE.md`
> - 加工 runbook (collector→chisha 四步 + 踩过的坑): [docs/data-pipeline.md](data-pipeline.md)
> - tagged schema 权威: `chisha/schemas.py`; 推荐链路字段消费: [docs/CONTRACTS.md](CONTRACTS.md)

## 全景 (4 stage, 2 repo)

```
 ~/waimai_data (真机 UI 自动化)                    ~/chisha (加工 + 推荐)
┌──────────────────────────────┐   scp / 手工   ┌──────────────────────────────────┐
│ Stage1 采集     Stage2 聚合   │ ─ output ───►  │ Stage3 摄入+打标   Stage4 推荐消费 │
│ 美团 App→菜单    per-loc 合并  │  *.json        │ loader→tag→backfill   recall→score │
│ state/<loc>/    output/*.json │                │ data/<zone>/*.json    →rerank(L3)  │
└──────────────────────────────┘                └──────────────────────────────────┘
```

每 stage 的产物边界清晰, 上一段的输出文件是下一段唯一输入, 中间无隐式共享状态。

## Stage 1 — 采集 (`~/waimai_data`, python-uiautomator2 + 真机 Android)

- **怎么采**: 状态机 (`collector/state_machine.py` + `anchors.py`) 驱动屏幕状态流转 `S0 主页 → S1 外卖频道 → S3 商家列表 → S_SHOP 店内菜单`, 逐家进店后 `menu_extractor_v3.py` 用几何 invariant (菜品列 cx/宽/高 + ¥ 锚点) 从 UI dump 抽菜名/价格/月售/分类。`S_RISK` 命中滑块验证 → 冷却退出。
- **怎么沉淀**: `progress.py` 增量落 `state/<loc>/`:每家店成功即原子写 `menus/<rid>.json` (rid = sha1(归一店名)[:10]) + append `restaurants.jsonl` 元数据 + 滚动更新 `checkpoint.json`。**断点续传**靠扫 `menus/` 全集: `status∈{ok,early_ok}` 且菜非空 = 完成, `partial/failed/risk_interrupted` 下次重采。
- **怎么去重 / 不漂移**: `seen_names` 跨 session 跳已采店 (含截断名前缀匹配兜底); brand cap 限同品牌每 location ≤2 家 (`brand_cache.json` 全局 + `brand_visits.json` per-loc), 把配额从重复连锁释放给独立店。
- **location**: `home`=家附近社区, `office`=深圳湾创新科技中心 (`collector/config.py`), state 目录与续传完全隔离。

## Stage 2 — 聚合 (per-location → output JSON)

- `tools/aggregate.py` / `collector/main.py` 扫 `state/<loc>/menus/` 全集 → **先**按截断/全名同店 dedup (必须在丢低菜之前) → 按菜品数倒排 → `extractor.py` 写 `output/<loc>_restaurants.json`。
- **产物 schema**: 顶层 `{app, collected_at, location:{name,label}, restaurants[]}`; 每店含元数据 (rating/月售/配送费/起送/时长/距离) + `menu_status` + `menu[]`; 每菜 `{category, name, price, image, monthly_sales?}`。
- 可选 `uploader.py` scp 到远程 OpenClaw skill 目录 (供未来 agent 接入)。
- **注意**: 聚合**未硬过滤**残缺店 —— `failed/partial/None` 状态店仍进 output (见下「断裂点 C」)。

## Stage 3 — 摄入 + 打标 (`~/chisha`, 见 data-pipeline.md 四步)

1. **loader** (`chisha/loader.py`): `output/*.json` → `data/<zone>/{restaurants.json, dishes_raw.json}`。归一化月售/距离/时长、抽 brand、按**稳定哈希 id** 去重 (rid=`r_`+sha1(归一店名); dish_id=`d_`+rid+sha1(归一菜名), D-099, 与采集端逐字一致 → 重采不漂移)。同店同归一菜名异价 = 真冲突, 隔离不发布直到 `conflicts_ack.json` 确认 (D-099.1, fail-loud)。`office→shenzhen-bay`, `home→home`。
2. **tag** (`scripts/tag_via_api.py`): `dishes_raw → dishes_tagged`。OpenRouter deepseek-v4-flash (D-037), batch 30 / 16 workers, 缓存绑有序 dish-id 清单 (D-099.3, 重采批内变了才重跑)。产出 = `cuisine` (16 枚举) + `nutrition_profile` (12 维营养画像, schemas.py 权威)。默认增量, 全量 `--force-version`。
3. **backfill** (`backfill_restaurant_category`): tagged 菜系 majority vote → `restaurants.json.category`。
4. **validate** (`scripts/validate_data.py`): `DishTagged` 全量 schema 校验 + 覆盖率 + 引用完整性, hard-fail。

## Stage 4 — 推荐消费 (`recall → score → rerank`)

- **加载**: `recall.load_zone_data(zone)` 每次按需读 `data/<zone>/{restaurants.json, dishes_tagged.json}` (无内存缓存)。
- **召回** (`recall.py`): 从菜品出发, L0 医学/伦理硬约束 + P1 偏好硬过滤 + 7 天主蛋白多样性过滤 → 按 `restaurant_id` 分桶 → 每店生成蔬/蛋白/主食 combo。空菜单店天然不出候选。
- **打分** (`score.py`): 15 维信号消费 `nutrition_profile.*` (油/蛋白/全谷/加工肉/甜酱/汤水/dish_role) + `cuisine` + `monthly_sales` (popularity) + `delivery_eta_min` + `feedback_recency` (D-098, 按 dish_id/rid 关联反馈)。
- **精排** (`rerank.py` + `refine.py`): L3 LLM (sonnet/opus, 非 flash) 读紧凑菜品行 + profile + refine_intent, 输出 rank/fit/risk_flags/一句理由。忠实纪律见 [chisha_faithful_refine_principle] / CONTRACTS。
- **id 作 join key**: `dish_id`/`restaurant_id` 贯穿 recall 分桶 → score 反馈查表 → rerank 编码 → feedback_store 反查。`logs/feedback/store.json` 靠 dish_id/rid 闭环; `logs/meal_log.jsonl` 仅落 canonical_name + main_ingredient_type (不落 dish_id, 见「断裂点 E」)。

## 现状数据量 (2026-05-26)

| zone | 采集 output 店 | chisha 店 | dishes (raw=tagged) | 残缺菜单店 (partial+failed+None) |
|---|---|---|---|---|
| shenzhen-bay (office) | 429 | 395 | 22,688 | 166 (42%) |
| home (home) | 142 | 142 | 8,088 | 47 (33%) |

tagged 覆盖率 100% of raw; monthly_sales=0 占 ~10% (部分真 0, 部分 parse 失败)。
**注意 (P0, 见断裂点 G)**: home 142 店全部是 shenzhen-bay 子集 (0 家独有), 且 129/142 店 distance 与 office 逐字相同 → home 采集疑似未切配送地址, 距离/eta 是深圳湾值。

## 已知断裂点与优化方向

> 按影响排序, 经 Opus 实证 + Codex 二审收敛 (2026-05-26)。严重度已按代码/数据核实校准, 非凭印象。

- **G. (P0, 实证) home 距离/eta 疑似采集污染**: 采集 output 里 home 142 店**全部**是 office 子集 (0 家独有), 129/142 店 distance 字符串与 office 逐字相同 (西贝印力中心 990m=990m / 马记永 4800m=4800m)。两地实际相距 ~12km (config gps), 距离不可能相同 → **home 采集时美团配送地址疑似未切到家附近社区, distance/eta 反映的是深圳湾**。后果: 在家点餐场景拿到的是 office 区餐厅 + 错的 ETA (score eta 维度直接吃这值)。**行动: 志丹确认采集时是否切地址 → 切对地址重采 home**。(此问题由追 Codex 的"跨 zone id 碰撞"线索挖出: id 碰撞本身不是 bug——同一物理店本该共享稳定 id; 真问题是 home 根本没采居住区。)
- **A. 标签地基质量无持续抽检 (高)**: `nutrition_profile` 全是 deepseek-flash 估计值 (`eval/` 有 171 条一次性横评, flash 88.9% → ~11% 字段误), 推荐 15 维多数建其上 (eta/price/popularity/feedback 不依赖标签, 实际影响低于"全军覆没")。缺口是无生产持续抽检。建议: 固化 ground-truth gate, 换模型/prompt 时跑准确率回归。
- **B. `restaurant.category` 全空 → L3 丢餐厅菜系信号 (已修正: 非死字段)**: 两 zone 店 category 全空 (D-099 重消费漏跑 backfill 第3步)。`rerank.py:599` 把 `category` 当餐厅 "cuisine" 喂给 L3 → 现在每次给 L3 一个空信号。**消费方真实存在**, 不是死字段。行动: 补跑 backfill (而非砍字段)。
- **C. 残缺/空菜单店残留 ingest (中, 已部分治理)**: 采集端 `_keep_for_output` 已过滤 0 菜/低残缺店, validate 仅对 0 菜店报 error (partial/failed 不 hardfail)。旧数据入库的空壳仍膨胀店数 (深圳湾 42% / 居住区 33% 残缺), backfill 在空店失败、debug UI 露脸。主链路无害 (recall 从菜出发)。是否清旧空店是产品选择。
- **D. 跨 repo 四步无单一入口 (中, scp 已自动)**: `uploader.py` 已自动 scp, 但 `loader→tag→backfill→validate` 无统一编排, 回填遗漏 (B) 就是结构性证据。建议: 一个编排脚本串四步, 末尾 validate 不过非 0 退出, 并加 category 空率 / 跨 zone distance 全等 等哨兵 (能自动抓住 G 类污染)。
- **E. `meal_log` 不落 dish_id (低)**: 确认只落 canonical_name + ingredient_type; 短链反馈通过 session 冷存取 dish_id 闭环未断, meal_log 缺口仅影响未来菜品级长期厌腻/复购分析。低成本补: 落盘加 dish_id。
- **F. 打标缓存 key 太弱 + 无 enum 归一化 (中)**: (1) 缓存只绑有序 dish_id 清单, **不绑 model name / prompt 版本 / category_raw** → 换模型或改 prompt 会静默复用旧标签 (Codex 提出, 成立)。(2) deepseek 偶发枚举越界值无确定性归一化层 (越界后重试 + 写 staged 不污染 live, 但仍需人工介入)。建议: cache key 加 model+prompt hash; merge 前加 enum 归一化 (已知值映射 + 未知值 warn)。
- **H. (Codex 提出, 已核实) 反馈落盘失败仅 print 不告警 (低-中)**: `web_api._remember_session_safe` catch 异常后 print 一行 (非"无日志", Codex 略夸大), docstring 明写"失败不阻断"是有意设计。真风险: session 冷存缺失 → 之后对该 session 的反馈无法 resolve combo, 静默 no-op (与 B-001/D-098"差评不生效"同源)。建议: 失败计数落结构化日志或在反馈页提示。
- **次要**: `monthly_sales` 真 0 与缺失 (parse 失败) 都映射成 0, popularity 无法区分"未知"与"冷门", 可能误降权热销菜 (~10% 菜受影响)。
