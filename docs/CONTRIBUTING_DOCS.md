# 文档维护准则 · chisha

> 目的：让文档不漂移、不重复、不腐烂。2026-05-16 按"读者分层"重构（详见 [decisions.md](decisions.md) 顶部说明）。

---

## 1. 四桶文档（按读者分）

| 桶 | 文件 | 主读者 | 写什么 | 写多长 |
|---|---|---|---|---|
| **A · 产品决策** | [decisions.md](decisions.md) | 你 | 产品方向 / 推翻历史 / 没选 B 方案的原因 | **3-5 行/条**，> 15 行就是塞实施 |
| | [PRD.md](PRD.md) | 你 | 产品定位 / 用户痛点 / 北极星 | 极少改 |
| | [ROADMAP.md](ROADMAP.md) | 你 | V1/V2/V3 边界 / 已砍清单 | 阶段切换时改 |
| **B · Agent 契约** | [CONTRACTS.md](CONTRACTS.md) | Coding agent 每次会话 | 跨文件隐含约束 / 反直觉规则 / 系统级 invariant | ≤ 200 行 |
| | [../CLAUDE.md](../CLAUDE.md) | Coding agent 每次会话 | 红线 / 常用命令 / 当前阶段焦点 | ≤ 100 行 |
| | [api.md](api.md) | Agent | 前后端 API 契约（V1） | 接口变化时改 |
| | [style-guide.md](style-guide.md) | Agent | `apps/web/` UI 文案 + 视觉系统 + 反模式 | UI 决策落地时改 |
| **C · 归档** | [archive/](archive/) | 历史考古 | Phase 0 旧 DECISIONS / IMPL_LOG / DESIGN / 等 | **不维护** |
| **D · 评测** | [../eval/](../eval/) | 复评 prompt 时 | 评测框架 + golden set + spec | 评测重做时改 |

---

## 2. 写新决策（活在 decisions.md）

**目标**：3-5 行。够说清"决定 + 一句话原因"就停。
- 自然展开 ≤ 15 行（真有方案对比时）
- **> 20 行就停下**，你在写实施。把实施细节丢给 git commit body / code 本身
- 无固定 4 段模板。想清楚就写，写不清楚说明决策本身没想清楚——别用模板撑场面
- superseded 就地标 `[已废弃 by D-NNN]`，**不删不挪**（保留推翻历史）

**示例（4 行版）**：
```markdown
## D-070 · 定位收敛到原则派 (2026-05-15)
砍"通用点餐推荐"，改服务已认了一套饮食方法论的人。
通用人群目标缺失没法刻画偏好；原则派痛点明确可外包。
推翻：之前隐含的"什么都行的人"路径。
```

---

## 3. 工程细节去哪？

**默认：不写文档，放代码。** 三个例外才进 [CONTRACTS.md](CONTRACTS.md)：

1. **跨文件隐含约束** — 改 A 文件破坏 B 文件预期，且 B 局部看不出依赖 A
2. **反直觉约束** — 代码"看起来"应该这样，但实际不能（踩过的坑）
3. **系统级 invariant** — 违反让管道静默错误

**不写**（无论多重要，代码已有）：
- 字段表 / schema keyset
- prompt 行号 / 参数值
- 测试列表 / 覆盖率
- batch 数 / timestamp / commit hash
- 文件改动清单

git log + grep 代码即权威。

---

## 4. 每次 D-XXX commit 后 checklist

1. **写到 decisions 还是 CONTRACTS？**
   - 产品方向 / 推翻历史 → `decisions.md`
   - agent 必须遵守的硬约束 → `CONTRACTS.md`
   - 两边都不属于 → 大概率你在写实施，git commit body 就够
2. **是否推翻旧决策？** 推翻就地标 `[已废弃 by D-NNN]`，不删
3. **是否需要联动？** ROADMAP 当前状态 / README 进度章节

---

## 5. 反 anti-patterns

- ❌ **写决策超过 20 行** → 你在塞实施。删掉重写
- ❌ **同内容在 decisions 和 CONTRACTS 都写一遍** → decisions 是 "为什么"，CONTRACTS 是 "必须遵守的硬约束"，互相 link 不重复内容
- ❌ **D-XXX 写完不更新 ROADMAP / README** → 决策与进度脱节是头号腐烂源
- ❌ **新加文档却不在 README 文档体系表登记** → 外人找不到等于不存在
- ❌ **PRD 频繁改** → 定位级变化才动 PRD，每次改要在 decisions 加一条说明

---

## 6. 阶段收口

V1 / V2 / V3 切换或每周一次 wrap-up 时：

1. **decisions.md 全文扫一遍** — 有 superseded 没改的 / 已废弃还在 active 状态的 → 修
2. **CONTRACTS.md 检查** — 新加的 invariant 是不是真的"代码看不出"，否则砍掉
3. **ROADMAP 当前状态** — 与最近 git log 对照，缺的补
4. **README 进度章节** — 与 ROADMAP 对齐

若用 `neat-freak` skill 自动整理，**调用前 prompt 加一句**："写决策 ≤ 15 行，超过就是实施。讲不完就丢弃，不要塞回旧 IMPL_LOG 归档"。

---

## 7. 编号约定

- D-XXX 全项目共享，新决策追加到 `decisions.md` 尾部
- 推翻型 D-NNN.M（如 D-046.1 是 D-046 后的修订）
- superseded 就地标 `[已废弃 by D-NNN]`，**不删不挪**
- 新建文档必须在 README 文档体系表登记
