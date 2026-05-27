# 数据流水线 · 采集后加工 (collector → chisha)

> 何时用: `~/waimai_data` 采集了新数据, 要重新消费进 chisha 供推荐链路用时。
> 单一权威是代码: schema 看 `chisha/schemas.py`, 参数默认值看各脚本 argparse。本文只讲**流程 + 命令 + 踩过的坑 + 验收**。

## 输入 / 输出

- **输入**: `~/waimai_data/output/{office,home}_restaurants.json` (collector 聚合产物, dict 含 `restaurants[]`, 每店 `menu[]`)。
  - `office_restaurants.json` → zone `shenzhen-bay`; `home_restaurants.json` → zone `home`。
- **输出** (推荐链路真正消费的): `data/<zone>/{restaurants.json, dishes_raw.json, dishes_tagged.json}`。

## 推荐入口: `scripts/refresh_from_collector.py` (D-100)

重采后整轮重消费**走这个编排器**, 不要手敲下面四步 (除非 debug / 部分重跑):

```bash
uv run python -m scripts.refresh_from_collector   # 串: preflight 契约校验 → 跨zone指纹哨兵 → loader 发布(全zone) → tag → backfill → validate
```

它在裸四步之上加了三道 fail-loud 护栏 (D-100): ①`collector_contract` 入口契约校验 (envelope shape/类型/`schema_version==1`/`normalized_name_version==SHOP_NAME_VERSION`, 无 grandfather); ②跨 zone **指纹哨兵** (共享 rid≥30 + 共享率≥80% + distance 逐字相同率≥80% + label 不同 → hard-fail, 抓 G 式采址污染); ③**publish 全 zone 后才 tag** (防单 zone 哨兵误判后白烧 LLM)。`ZONE_MAP` (office→shenzhen-bay / home→home) 在脚本常量里 (消费端语义)。任一步非 0 退出。

## 底层四步 (orchestrator 内部就是这四步, 手动 debug / 部分重跑时直接调)

```bash
# 1. 消费/归一化: 美团 output → restaurants.json + dishes_raw.json
#    (解析月售/距离/时长、抽品牌、稳定哈希 id (D-099)、同店去重、空 category 待回填)
#    冲突未确认会 block (退出非0, 写 dish_id_conflicts.json + _staged/), 审阅后把 key
#    加进 data/<zone>/conflicts_ack.json 再重跑。
uv run python -m chisha.loader ~/waimai_data/output/office_restaurants.json shenzhen-bay
uv run python -m chisha.loader ~/waimai_data/output/home_restaurants.json   home

# 1b. (一次性迁移, 仅 id 算法/归一化版本变时) 旧标签按 (新rid,新dish_id) 重映射免重打:
#     先单跑第 1 步看冲突报告并 ack, 再跑迁移 (快照旧数据 + 发布 active raw + 预填 tagged)
uv run python -m scripts.migrate_stable_ids all    # 之后第 2 步增量补 needs_tagging

# 2. LLM 打标: dishes_raw.json → dishes_tagged.json (营养画像 + cuisine)
#    默认 deepseek-v4-flash / batch 15 / 8 workers (D-101: 30/16 实测截断超 8192 token
#    + 并发限流空响应, home 重采 24/28 batch 挂; 15/8 后 56 batch 0 失败)
#    增量: 默认只打 tagged 里缺的; 全量重打加 --force-version
uv run python -m scripts.tag_via_api all

# 3. 回填餐厅菜系: tagged 菜系 majority vote → restaurants.json.category
uv run python -c "from chisha.loader import backfill_restaurant_category as b; \
  print(b('data/shenzhen-bay/restaurants.json','data/shenzhen-bay/dishes_tagged.json')); \
  print(b('data/home/restaurants.json','data/home/dishes_tagged.json'))"

# 4. 验收: DishTagged schema 全量校验 + 覆盖率
uv run python -m scripts.validate_data
```

## 全量重消费的红线坑 (踩过, 别再踩)

1. **~~id 按文件位置分配~~ → 稳定哈希 id (D-099 已解, 2026-05-26)**: id 现在 = `r_+sha1(归一店名)` / `d_+rid+sha1(归一菜名)`, 重采→同店/同菜 id 不变, 历史反馈/标签永远映射得上。残留注意:
   - **打标缓存**: 缓存绑**有序 dish-id 清单** (D-099.3), 重采后批内菜变了会自动重跑, 无需手清; 但 id 算法本身变 (归一化版本 bump) 时建议清 `.claude/v3_tagging/<version>/<zone>/` 免堆陈旧批文件。
   - **历史反馈/偏好**: 同店同菜 id 稳定 → `logs/feedback/store.json` + `logs/meal_log.jsonl` 的旧 id 跨重采仍对得上, 不再错投 (这正是 D-099 的目的)。店**改名**会换 rid → 靠 `data/aliases.json` 人工绑旧名兜底 (D-099.2)。
   - **同名异价 SKU**: 同店同归一菜名但价格不同 (截断名 / 促销) = 真冲突, loader 隔离不发布直到 `conflicts_ack.json` 确认 (D-099.1); 已知 office 5 个, 见 `data/shenzhen-bay/dish_id_conflicts.json`。

2. **LLM 偶发枚举越界值** (~0.3%): deepseek 会输出词表外值 (cooking_method 如 卤/焗/干煸、cuisine 如 杭州/台湾菜、protein 如 `'60+'` 字符串)。**D-101 已止血**: tag_via_api `_finalize_write` **记录级隔离** — 单条越界写 `dishes_tagged.quarantine.json` (不再 hard fail 整 zone 写 _staged), valid 照进 active; 非菜品 (餐具/包装/营销 → `cooking_method='其他'`) 由 `non_dish_rules` 在 loader 打标前 (Layer1) + tagger (Layer2) 两层隔离。**残留 TODO**: 隔离对"非菜"和"真菜罕见做法 (卤/焗/干煸 是合法做法只是不在 9 值枚举)"一视同仁 → 后者会被**误隔离丢失**这道真菜。确定性 enum 归一 (卤→炖/煮 之类映射后保留) 仍未做 —— 当前隔离是"安全网"非"修复"。临时全量重打补漏: `--force-version` (绕过 quarantine skip)。

3. **空菜单店** (collector failed/partial → 0 菜餐厅): 会 ingest 成无菜的 restaurant 行, `validate_data` 标 ✗。属既有可容忍状态 — `recall` 从菜品出发分桶, 空店天然不出候选, 主链路无害; 只在直接遍历 restaurants 的视图 (debug UI 列表) 露脸。要不要过滤是产品选择, 默认留存 (不偏离历史行为)。

## 并发与成本 guidance

- 默认 `batch=15 / workers=8` (D-101 收口稳定值)。**别盲目调高**: `batch=30` 的 JSON 输出会超 `max_tokens=8192` 截断 (JSONDecodeError); `workers=16` 两 zone 背靠背会把 endpoint 打到限流空响应 (home 重采实测 24/28 batch 挂)。`_call_one_batch` 有 3 次指数 backoff, 但截断/限流持续时救不回。要提吞吐先确认单批输出不撞 token 顶 + 分 zone 错峰。
- OpenRouter 撞月额度会 403 雪崩 → 提额后清缓存 resume 增量续打补齐。
- 用 deepseek-v4-flash 时全量 ~3 万菜成本可忽略 (几分钱~$1 级)。

## 验收清单

- `validate_data`: 两 zone tagged 覆盖率 = 100% of raw; DishTagged 0 违规 (空菜单店的 ✗ 属既有, 非新增)。
- 冲突报告 `data/<zone>/dish_id_conflicts.json` 已审阅, 未确认冲突清零 (否则 loader 不发布)。
- (稳定 id 后) `logs/feedback/store.json` + `logs/meal_log.jsonl` 旧 id 跨重采自动对齐, **无需迁移**; 仅店改名需在 `data/aliases.json` 补 alias。
- `restaurants.json.category` 已回填 (空菜单店除外)。
