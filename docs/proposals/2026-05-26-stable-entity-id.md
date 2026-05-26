# 提案: 稳定实体 id (跨重采不漂移)

> 状态: **已落地** (2026-05-26, worktree `d099-stable-entity-id`)。决策入 `docs/decisions.md` D-099~D-099.3, 流水线坑已改 `docs/data-pipeline.md`。
> 落地差异 (vs 提案): 数据已重采 (office 409→429raw→395unique); Codex pressure-test 加了**原子发布 ack 状态机** (未确认冲突 block 不发布) + **dedup 内容指纹 tie-break** (不用输入顺序) + 迁移**ingest 前快照** + 多源旧标签冲突判 ambiguous; 同名冲突签名只看价格不看销量。以下为定稿时提案原文, 留作溯源。

## 问题
`chisha/loader.py::normalize()` 按**文件位置**发 id (`r_{i:03d}` / `d_{i:03d}_{j:03d}`)。collector 每双周/月重采一次, 餐厅顺序/数量一变 → id 整体洗牌 → `logs/feedback/store.json`(冷存 sessions)、`logs/meal_log.jsonl`、`long_term_prefs`、D-098 `feedback_signal` 全部错位 (旧 id 偶然撞新店, boost/penalty 错投)。

**目标**: 重采→重消费后**同店/同菜 id 不变**, 历史反馈永远映射得上; 顺带让打标变真增量。

## 已确认事实 (实证)
- collector output **无平台商家 id**, 餐厅自然键只有 `name`, 菜品只有 `name`(+price)。
- collector 已有稳定 rid: `collector/visit_history.py::restaurant_id(name) = sha1(normalize_shop_name(name))[:10]`, 用于 `state/<zone>/menus/<rid>.json` 命名。chisha 侧用同算法 hash output 店名, office 409 家 **396 命中采集端 menus/**, 精确复现 (`2046（科技园海王2店）`→`005155d2c7`)。
- output **有重复店**: office 409 条 → 383 唯一店名 (位置 id 当两条, 稳定 id 归并)。
- **跨 zone 100% 重合**: home 142 家全部与 office 同 rid (5-25 state merge 产物 + 配送圈重叠)。

## 核心方案
- **餐厅 id** = `"r_" + sha1(normalize_shop_name_v1(raw_name))[:10]` — 与采集端 rid 逐字一致。
- **菜品 id** = `"d_" + rid + "_" + sha1(normalize_dish_name_v1(raw_name))[:8]` — restaurant-scoped。
- `normalize_shop_name_v1` 必须**逐字复现** collector `text_norm.py` (NORMALIZED_NAME_VERSION=1): ①Unicode 空白(NBSP/U+2006/U+3000/\t\r\n)→0x20 ②零宽(ZWSP/ZWNJ/ZWJ/WJ/BOM)→删 ③全角括号（）→() ④collapse 连空格 ⑤strip。**显式不动**大小写/中点/标点。chisha 不 import waimai_data(独立 repo), 拷这 ~20 行进 loader, 注释标同源 + 版本号。
- `normalize_dish_name_v1`: **当前未定义, 落地前需单独定版** (菜名归一化, 至少复用店名那套空白/零宽规则)。

## 定稿决策 (落地时入 decisions.md)

### D-099 稳定实体 id 以采集端名称规范为唯一契约
- 公式见上; `normalize_shop_name_v1` 逐字复现 collector 并记版本, 不另造简化规则。
- 中期可推动 collector output 直接携带 `rid`, chisha 不从 state 完整名反推身份。

### D-099.1 菜品唯一性 + 重复记录 fail-loud
- `dish_id` = 同店内一个逻辑菜名; **价格/销量变化不改 id**。
- 同 rid 下相同归一菜名出现多条、或不同菜名 8 位哈希碰撞 → **隔离待人工裁决**, 不加顺序后缀、不把 price 混入 key。
- 同快照内重复餐厅去重取**单一权威记录**: `menu_status` 优先级 `ok > early_ok > partial > failed` → `menu_count` → 稳定 tie-break; **不取菜单并集** (并集会把下架/异常菜留成有效菜, 污染召回与价格过滤)。

### D-099.2 改名 / 截断 / 跨 zone 身份语义
- 店改名 → 新 rid; 仅靠**人工确认的 alias 表**把旧名绑到 canonical rid, 禁止模糊自动归并分店名。(D-098 强负反馈 30 天内剔店、60 天内影响得分, 改名会绕过保护 → alias 兜底必要。)
- output 截断名作输入键须审计同名多实体冲突; 归一化/截断**版本变化视为迁移事件**。
- `rid` = **全局门店身份**, zone 仅配送上下文; 同 rid 反馈/近期消费**允许跨 zone 生效**(同店同菜, 差评跨 zone 该生效), 前提是碰撞审计确认确为同一实体。

### D-099.3 增量打标复用标签, 不复用过期 raw 状态
- 仅**新 dish_id 或 tag_version 变**才调 LLM; 价格/销量 raw 变化不改 id 但要刷新值。
- 每次 ingest 后以当前 `dishes_raw` **重建活动 `dishes_tagged`**: 复用旧营养标签 + 刷新 raw 字段 + **删除 raw 中消失的菜**; batch 缓存须绑 dish-id 清单 (非仅批号/长度)。
- `recall/score/feedback_signal` 对 id 仅做**字符串相等/映射查询** (已审计确认无 `r_\d+` 数字格式假设, `r_<hex>` 兼容); 不得新增数字格式解析。

## 迁移步骤 (一次性; feedback 已清空, 无历史需迁移)
1. 改 `loader.normalize` 用稳定 id + 实现 dedup 权威记录选择。
2. 重 ingest 两 zone (秒级)。
3. `dishes_tagged` 旧标签按 (rid + 菜名) **重映射到新 id 免重打 LLM**; 兜底增量重打。
4. `validate_data` 全绿; 更新 `docs/data-pipeline.md`。

## 实施清单 + 测试 (落地范围, 不止 loader)
- `chisha/loader.py`: 稳定 id + dedup + alias 钩子。
- `scripts/tag_via_api.py`: 活动集重建 (删消失菜) + batch 缓存绑 dish-id 校验 (**必须纳入**, 别只改 loader)。
- alias 表载体 (小 json, 人工维护)。
- 一次性迁移脚本 (标签重映射)。
- 测试: hash id 稳定性 / 跨 zone 同 rid / 下架菜删除 / 价格变不改 id / dedup 权威记录选择 / 哈希碰撞 fail-loud。

## 待盯 open items
- **菜名截断**: output 名疑似被截断(如"星河 Cocop[ark]"); 实证 396 命中说明当前截断确定性, 但若 collector 截断逻辑变 → rid 漂移。最稳是推动 collector output 直接出 rid。
- **home=office 100% 重合**: 疑似 5-25 state merge 污染了 home output; 落地前确认 home 采集是否独立, 否则 home zone 数据本身存疑 (采集侧问题, 非本提案范围)。
- **normalize_dish_name_v1 未定义**: 落地前先定菜名归一化规则 + 版本。
