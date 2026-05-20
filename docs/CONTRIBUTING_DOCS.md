# 文档维护准则 · chisha

> 主读者: 志丹自查 + 整理文档时的 agent.
> CLAUDE.md "文档纪律" 段是这份文档的红线摘要; 此处是**完整规则 + 反 antipattern**.

---

## 1. 四桶分层 (按读者)

| 桶 | 文件 | 写什么 | 长度上限 |
|---|---|---|---|
| **产品决策 (你)** | `decisions.md` / `PRD.md` / `ROADMAP.md` | 产品方向 / 推翻历史 / 没选 B 方案的原因 | 单条 3-5 行, > 15 行就是塞实施 |
| **Agent 契约 (Claude/Codex)** | `CONTRACTS.md` / `../CLAUDE.md` / `api.md` / `style-guide.md` | 跨文件约束 / 反直觉规则 / 红线 / API 契约 | CONTRACTS ≤ 200 行, CLAUDE ≤ 100 行 |
| **归档 (frozen)** | `archive/` / `proposals/archive/` / `specs/archive/` | Phase 0 历史 | **不维护** |
| **评测** | `../eval/` | 评测框架 + golden set | 评测重做时改 |

---

## 2. 五条硬规则

1. **决策 ≤ 15 行**. 超过就是你在写实施, 删掉重写. superseded 就地标 `[已废弃 by D-NNN]`, **不删不挪**.
2. **不写代码已有的**: 字段表 / schema keyset / prompt 行号 / 参数值 / 测试列表 / batch 数 / commit hash / 文件改动清单. git log + grep 即权威.
3. **archive 是 frozen, 不是必读**. 冲突时以 `decisions.md` + `CONTRACTS.md` 为准. 禁止把 archive 列为"改 X 前必读". 允许做 `[D-XXX](archive/...)` anchor 引用 (wiki 内链, 不强制读).
4. **decisions ↔ CONTRACTS 不重复内容**. decisions 写"为什么", CONTRACTS 写"必须遵守的硬约束", 互相 link.
5. **新加文档必须在 README 文档导航登记**. 外人找不到等于不存在.

---

## 3. 反 antipattern

- ❌ 决策 > 20 行 → 你在塞实施
- ❌ 同内容在 decisions 和 CONTRACTS 都写一遍
- ❌ D-XXX 写完不更新 ROADMAP / README
- ❌ 内部工具的工程契约 (debug 台 / sandbox 实现细节 / trace schema / worktree 教训) 写进 `decisions.md` — 这些归 CONTRACTS
- ❌ "Wave N 重构" / "本周 sprint" 这种内部 timeline 黑话留在文档里 — 未来读者 0 价值
- ❌ PRD 频繁改 → 定位级变化才动 PRD

---

## 4. 阶段收口

V1 / V2 / V3 切换或每周 wrap-up 时:

1. **decisions.md 扫一遍** — 有 superseded 没改的 / 工程细节误入的 → 修
2. **CONTRACTS.md 检查** — 新加的 invariant 是不是真"代码看不出", 否则砍
3. **ROADMAP + README** 与最近 git log 对照, 缺的补
4. 若用 `neat-freak` skill 自动整理, **prompt 加一句**: "≤ 15 行原则, 讲不完就丢弃, 不要把实施细节塞回 archive"

---

## 5. 编号约定

- `D-XXX` 全项目共享, 追加到 `decisions.md` 尾部
- 推翻型 `D-NNN.M` (如 D-046.1)
- `B-NNN` bug · `F-NNN` feature · `I-NNN` idea 在 `BACKLOG.md`
