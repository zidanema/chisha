# 提案: collector↔chisha 接口契约硬化 (防字段漂移 / id 漂移 / 采址污染)

> 状态: **已落地** (2026-05-26, D-100)。Batch A (生产端 waimai) + Batch B (消费端 chisha) 均完成, 见 decisions.md D-100。残留真机/全链路验收待周末重采居住区。
> 背景: 端到端数据流 review 见 `docs/data-flow.md`; 触发事件 = 断裂点 G (home 采址污染, home 已 purge 待重采)。
> 落地方式: 独立 session (建议 worktree, 见 [[chisha_worktree_sync_pitfall]])。分两批 —— **Batch A 赶志丹周末重采前**, Batch B 重采后 ingest 前。

## 问题

waimai_data(生产) ↔ chisha(消费) 之间是**隐式契约**, 三处零防护:

1. **归一化逻辑双份 copy**: waimai `collector/text_norm.py::normalize_shop_name` (NORMALIZED_NAME_VERSION=1) 与 chisha `loader.py::_normalize_name_v1` (SHOP_NAME_VERSION=1) 独立实现, 仅注释对齐。实测当前 5/5 用例 byte 级一致 (未漂移), 但任一端单边改规则 → 稳定 id 静默漂移 → 历史反馈/标签全部 mis-join (D-099 价值崩塌)。
2. **输出无 schema/版本, loader 零输入校验**: output 顶层只有 `{app, collected_at, location:{name,label}, restaurants[]}`; `load_raw` 只 `json.load`, 字段重命名/类型变/缺失全部静默吞成 None/0。
3. **无采集 provenance**: output 只记配置标签 `location.name` ("家附近社区"), 不记采集时美团实际配送地址 → 标签对但地址错 (G) 从文件无法自检。`grep chisha` 在 waimai 全 repo = 0 命中, producer 无下游意识。

**目标**: 把"静默出错"全部变成"响亮报错", 且让周末重采自带可自验的地址 provenance。自用阶段 (D-097) 不上企业级, 不抽共享包。

## 已确认事实 (实证)

- 真 GPS 拿不到 (真机 `set_gps_location` no-op); 但**实际配送地址文本拿得到** (`_verify_location` 已读 `txt_address_info`, 现只返 bool 没写出)。
- `ensure_at_food_list()` 在 S3 阶段不调 `_verify_location()` → 若只靠碰巧过 S1, `observed_address_text` 常为 null。软观测须保证采前主动观测一次。
- loader.py **不在** high-risk 13 模块白名单 (api/recall/score/rerank/refine/l1_extractor/sandbox/clock/data_root/trace_store/debug_what_if/web_api/feedback_signal); 但受 D-099 数据身份契约约束, 改它仍走设计 review + commit diff review。
- 现有 shenzhen-bay output 无 version/schema 字段 (加断言会 fail → 见 D2)。

## 核心方案 (5 项, 按 ROI)

| 编号 | 项 | 优先级 | 治什么病 |
|---|---|---|---|
| C4 | 采址 provenance + 消费端指纹哨兵 | P0 | 防 G 复发 (已实证发生) |
| C3 | output schema_version + loader 窄契约校验 | P1 | 字段改名/类型漂移 |
| C2 | normalized_name_version 写出 + loader 断言 | P1 | 归一化单边改→id 漂移 |
| C1 | waimai 下游契约文档 | P2 | producer 无下游意识 (C2/C3/C4 的说明配套) |
| C5 | location→zone 映射沉淀一处 | P3 | 折叠进 refresh 脚本, 不独立立项 |

**关键设计决策**: C2 与 C3 治不同病, 都留 (C2 防 id 语义漂移, C3 防 shape 漂移; 版本号没变但归一化实现被误改时 C3 抓不到, 故 C2 不可省)。C3 用**窄契约**: 只校验 required 字段 + 类型, **允许新增字段** (免 producer 加非破坏字段就阻断消费)。

## 设计细节 (落地照此, 不再纠结)

- **D1 envelope 新字段**: `schema_version` = integer `1` (非字符串非语义化); `normalized_name_version` 取 `collector.text_norm.NORMALIZED_NAME_VERSION`, 消费端比对 `chisha.loader.SHOP_NAME_VERSION`; `location` 下新增 `observed_address_text` + `address_observed_at` + `address_observation_status` (**不用 verified_ 前缀**, 软版只观测不判定)。
- **D2 grandfather**: 选 **(b) 重导出** office output 带新 envelope, 地址观测填 `null` / status=`unobserved`; **loader 不留永久缺字段放行口** (避免技术债)。
- **D3 指纹哨兵判定** (区分"正常跨 zone 同店共享 rid, D-099.2 允许" vs "G 式全量克隆"):
  - **hard fail**: 两 zone 共享店 ≥ 30 **且** rid 共享率 ≥ 80% **且** distance 完全相同率 ≥ 80% **且** location.label 不同。
  - **warn**: 共享店 ≥ 20 且 distance 相同率 ≥ 50%。
  - (G 当时: 共享 142, distance 逐字相同 129/142=91% → 会被 hard fail 拦住。)
- **D4 `collector_contract.py`**: 纯边界校验器, **不进** high-risk 白名单; 在 `docs/CONTRACTS.md` 记一笔。但 `loader.py` 集成它时仍走 diff review。
- **D5 zone 映射**: 放 `scripts/refresh_from_collector.py` 常量 (zone 映射是消费端语义, producer 不该拥有); 不放 data_root.py, 不单建 config。

## 落地批次

### Batch A — 重采前 (waimai 侧, 零 high-risk, 赶周末)

- **A1 契约落档**: 新建 `waimai_data/OUTPUT_CONTRACT.md` + CLAUDE.md 加链接。写死: ①output 字段是下游契约, 不可随意改名; ②`text_norm` 改动 = 跨 repo 迁移事件 (须同步 chisha `SHOP_NAME_VERSION` + 走 `scripts/migrate_stable_ids`); ③location→zone 映射归属在 chisha。验收: 文档字段与当前 output 样例一致。
- **A2 输出 envelope**: 改 `collector/extractor.py::build_output()` 加 D1 字段。验收: 新 output JSON 含 schema_version / normalized_name_version / location.observed_* 三字段。
- **A3 软地址观测**: 改 `collector/navigator_meituan.py` + `main.py`, 采前主动观测一次配送地址文本写入 envelope, **软版只记录不判定** (status ∈ observed/unobserved)。验收: 一次真机采集 output 里 observed_address_text 非 null。
- **A4 重导出 office**: 用新 envelope 重生成 `output/office_restaurants.json` (D2-b), 地址 status=unobserved。验收: 旧 office 文件升级到 schema_version=1。

### Batch B — 重采后 / ingest 前 (chisha 侧)

- **B1 输入契约校验器**: 新建 `chisha/collector_contract.py` (pydantic 窄契约: 顶层 + restaurant + menu item required 字段/类型, 允许新增; 校验 schema_version + normalized_name_version)。CONTRACTS.md 记一笔。验收: 缺字段/类型错/版本不匹配单测全 fail-loud。
- **B2 loader 集成**: `loader.load_raw()` 调 collector_contract 校验 + 断言 `normalized_name_version == SHOP_NAME_VERSION`。**走 diff review** (D-099 契约)。验收: 喂旧无版本文件直接 fail (无 grandfather 口); 喂 Batch A 新文件通过。
- **B3 preflight 哨兵 + 编排**: 新建 `scripts/refresh_from_collector.py`: 内置 D5 zone 映射常量 + D3 指纹哨兵, 串 `preflight → loader → tag → backfill → validate`, validate 不过非 0 退出。验收: 喂 G 式克隆数据触发 hard fail; 正常两 zone 数据放行。

## 验收总线

- 周末重采居住区: 新 home output 的 `observed_address_text` ≈ 家附近社区, **且** B3 preflight 指纹哨兵不报警 (新 home 与 office 共享店少 / distance 不同) → 证明真采了居住区。
- 任一端单边改归一化版本 → ingest 立即 fail-loud (不再静默漂移)。
- output 字段改名/类型变 → loader 入口 fail-loud (不再 tag 后才暴露)。

## 未决 / 升级触发

- 抽共享归一化包: 自用阶段不做; 触发条件 = 出现第 3 个消费者, 或归一化规则频繁演进。
- A3 软观测稳定后, 可收紧成 producer 侧硬 gate (地址不匹配不发布)。
