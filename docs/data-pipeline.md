# 数据流水线 · 采集后加工 (collector → chisha)

> 何时用: `~/waimai_data` 采集了新数据, 要重新消费进 chisha 供推荐链路用时。
> 单一权威是代码: schema 看 `chisha/schemas.py`, 参数默认值看各脚本 argparse。本文只讲**流程 + 命令 + 踩过的坑 + 验收**。

## 输入 / 输出

- **输入**: `~/waimai_data/output/{office,home}_restaurants.json` (collector 聚合产物, dict 含 `restaurants[]`, 每店 `menu[]`)。
  - `office_restaurants.json` → zone `shenzhen-bay`; `home_restaurants.json` → zone `home`。
- **输出** (推荐链路真正消费的): `data/<zone>/{restaurants.json, dishes_raw.json, dishes_tagged.json}`。

## 四步流水线 (全用现成工具, 不要新写脚本)

```bash
# 1. 消费/归一化: 美团 output → restaurants.json + dishes_raw.json
#    (解析月售/距离/时长、抽品牌、按位置分配 id、空 category 待回填)
uv run python -m chisha.loader ~/waimai_data/output/office_restaurants.json shenzhen-bay
uv run python -m chisha.loader ~/waimai_data/output/home_restaurants.json   home

# 2. LLM 打标: dishes_raw.json → dishes_tagged.json (营养画像 + cuisine)
#    默认 deepseek-v4-flash / batch 30 / 16 workers (见 scripts/tag_via_api.py)
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

1. **id 按文件位置分配** (`r_{i}` / `d_{i}_{j}`, 见 `loader.normalize`)。新采集顺序/数量一变, id 整体重映射, 与旧数据**不对应**。后果与对策:
   - **打标缓存撞车**: 全量重打前先清 `.claude/v3_tagging/<version>/<zone>/` batch 缓存 + 用 `--force-version`/`--no-resume`, 否则旧 `batch_NNNN` 索引会复用到错的菜。(merge 用 dish_id 幂等覆盖, 同 delta 集合内 resume 安全。)
   - **历史反馈/偏好污染** (重消费后**必处理**, 否则下次推荐错投): `logs/feedback/store.json` 的 sessions 冷存 + `logs/meal_log.jsonl` 存的是旧 restaurant_id/dish_id。新旧都用 `r_NNN` 格式 → 偶然撞 id → D-098 反馈短链路(`feedback_signal`)和 `long_term_prefs` 的 boost/penalty 错投到新店。两条路: 清空这些 runtime log (干净但丢历史反馈) / 按店名重映射旧 id (保住反馈, 店还在才行)。这两个文件被 gitignore, 不进 commit, 但运行时仍读。

2. **LLM 偶发枚举越界值** (~0.3%): deepseek 会输出词表外值 (cooking_method 如 卤/焗/干煸、cuisine 如 杭州/台湾菜、protein 如 `'60+'` 字符串)。`validate_data` 是 hard fail 且逐字段只报第一个 → 必须全量扫 `DishTagged` 收齐再确定性映射到 enum (改 cuisine 后要重跑第 3 步)。建议: 把归一化沉淀进 `tag_via_api` merge 前的后处理 (已知值映射、未知值 log warn 不 crash), 免得每次手 patch。

3. **空菜单店** (collector failed/partial → 0 菜餐厅): 会 ingest 成无菜的 restaurant 行, `validate_data` 标 ✗。属既有可容忍状态 — `recall` 从菜品出发分桶, 空店天然不出候选, 主链路无害; 只在直接遍历 restaurants 的视图 (debug UI 列表) 露脸。要不要过滤是产品选择, 默认留存 (不偏离历史行为)。

## 并发与成本 guidance

- 瓶颈是**单请求生成延迟** (~30 菜/批的 JSON ≈ 120s), 非限流。吞吐 ≈ 并发/延迟, 加 worker 近似线性。`--workers 48` 实测对 16 拿到干净 3× (无 429)。
- OpenRouter 撞月额度会 403 雪崩 → 提额后清缓存 resume 增量续打补齐。
- 用 deepseek-v4-flash 时全量 ~3 万菜成本可忽略 (几分钱~$1 级)。

## 验收清单

- `validate_data`: 两 zone tagged 覆盖率 = 100% of raw; DishTagged 0 违规 (空菜单店的 ✗ 属既有, 非新增)。
- 重消费后: 已处理 `logs/feedback/store.json` + `logs/meal_log.jsonl` 旧 id (清空或重映射)。
- `restaurants.json.category` 已回填 (空菜单店除外)。
