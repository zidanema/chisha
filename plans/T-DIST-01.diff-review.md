# T-DIST-01 Sprint B 落地 — diff review (commit 前)

> 给 codex review 用. Sprint A (history rewrite 部分残留) + Sprint B 全部已落地, 现需 cumulative diff review.

## 范围

git log --oneline bd007be..HEAD (Sprint A R2 之后的所有 B 工作):

```
535180c fix(T-DIST-01 B.7): wheel ship profile.yaml 模板 + 严化 legacy state 判定
251b07f feat(T-DIST-01 B.6): wheel build sha256 + transport docs + dist/ gitignore
e18db22 feat(T-DIST-01 B.5c): onboard ephemeral dry start (scope=ephemeral + tmp state 隔离)
f2d9009 feat(T-DIST-01 B.5b): user-level zone/methodology loader + 撞名 fail-loud + 留位 API
b1355ea test(T-DIST-01 B.4 跟修): monkeypatch Path.home 防 e2e 写真 HOME
49aa3af feat(T-DIST-01 B.5a): chisha onboard 基础 (profile + skill + doctor)
bc60437 feat(T-DIST-01 B.3+B.4): SKILL.md 同步新 CLI + install-skill 走 user-level
fdf55ea feat(T-DIST-01 B.2): chisha 顶层 CLI 入口
8016a8f feat(T-DIST-01 B.0+B.1): wheel build spike + install_root 抽象 + callsite migration
```

## 完工验收 (B.7)

- [x] **干净环境**: `uv tool install ./dist/chisha_meal-0.1.0-py3-none-any.whl` 在临时 HOME 装上, 注册 `chisha` 可执行
- [x] **chisha doctor 全绿**: `install_data_manifest_status=ok` / `user_resource_status=[]` / `state_root_writable=true` / `legacy_state_pending_migration=false` / `sandbox_enabled=false` / `scope_ready=true`
- [x] **chisha onboard --zone shenzhen-bay 全绿**: profile written → skill installed → doctor.ok → dry_start "start → resolved"
- [x] **`~/.claude/skills/chisha-meal/SKILL.md` 含 `chisha agent` (新 CLI)**, 不含 legacy `uv run python -m chisha.agent_cli`
- [x] **User-level lookup 撞名 fail-loud**: zone (collision/not_found) + methodology (collision/not_found) 4 case PASS
- [x] **Doctor 分报字段**: `install_data_manifest_status` (改名) + `user_resource_status` (新增, list of {kind,name,status,note})
- [x] **baseline_l2_snapshot 0-diff** (B.1 ref vs B.7, top1 大米先生 score=2.457413)
- [x] **pytest 1221 passed** (1185 B.1 + 6 B.2 + 6 B.3+4 + 8 B.5a + 16 B.5b + 跟修 0, all green; B.0/B.6/B.7 不加测试)
- [x] **wheel content gate**: positive 7/7 (rerank_system.md / parse_refine_intent_v2.md / harvard_plate.yaml / data/manifest.json / shenzhen-bay/{restaurants,dishes_tagged}.json + profile.yaml), negative 0 (apps/plans/docs/tmp/logs/eval/tests/scripts/.claude/dishes_raw/review_sample/conflicts_ack/non_dish_quarantine/dish_id_conflicts 全不在)
- [x] **methodology schema/template/validate 都 NOT_IMPLEMENTED exit 1**

## 重点 design 偏离 + risks

**A. install_root 智能探测 (vs plan 字面 Path(__file__).parent)**
plan 字面实现在 dev 时返 chisha/ 包目录, 但 dev 没 chisha/prompts (prompts 在 repo root level), 直接 return parent 会破 dev. 改成两布局智能: 优先 chisha/<resource>/ 存在则用包目录 (wheel), 否则 fallback 包目录父级 (dev = repo root). 已验 dev 行为 0-diff + wheel install 正确解析.

**B. force-include 旁路 hatch exclude → per-file 枚举**
hatch 的 `[tool.hatch.build.targets.wheel.force-include]` 旁路 exclude 规则. 不能 force-include 整 data/, 否则 dishes_raw.json (4.7MB) / review_sample.* / conflicts_ack.json 等离线打标中间产物全部混入 wheel. 改成 per-file 枚举 7 项 (manifest + aliases + zone/{rest,tagged} + profile.yaml + prompts dir + profiles/methodologies dir). 维护成本: 新 zone 需手动加, 没自动 CI 校验. P2 防线: build_manifest 可加 manifest_zones vs wheel_content 比对 (推迟 T-DIST-02).

**C. state_root.project_root() 委托给 install_root() — wheel 行为正确**
"root==install_root 判生产" 在 wheel 模式 install_root=site-packages/chisha. 外部传非该值 → state 落 root; 显式 install_root 或 None → ~/.chisha. 测试隔离走 monkeypatch default_state_root → tmp_path (conftest autouse).

**D. user-level loader 同物理路径兜底 (state==install)**
recall._resolve_zone_dir / methodology._methodology_path 都判 `user_dir.resolve() == install_dir.resolve()` 不算 collision. 防测试单根布局/legacy 模式误报. 用户主动设 `CHISHA_STATE_ROOT=install_root` 真撞名也会被吞 — P3 风险 (用户主动设这个 env 视为承担风险).

**E. doctor 字段 breaking rename (无 grandfather)**
`data_manifest_status` → `install_data_manifest_status` 删旧名, 不留 alias. 配对新增 `user_resource_status`. SKILL.md 没引该字段; downstream 只有测试 + 已同步 (test_onboard.py).

**F. ephemeral scope 隔离机制**
cmd_onboard step 4 走 tempfile.TemporaryDirectory + os.environ['CHISHA_STATE_ROOT']=tmp + cmd_start(scope=ephemeral). try/finally 还原 env, contextmanager 退出删 tmp. zone data 走 install_root (不受影响), state (round/trace/meal_log) 全落 tmp 跑完即删. 验证: tmp leak none + real state_root logs/agent_rounds 不被污染.

**G. has_legacy_state 严判 (vs profile.yaml 单独标记)**
plan 早期 _MIGRATE_MAP 把 profile.yaml 当 legacy marker. 但 wheel ship profile.yaml 模板后, 误触发 legacy_pending → doctor 永红. 改用 has_legacy_state: logs/ 有内容 OR feedback_history.jsonl 非空 OR long_term_prefs.json 存在 (profile.yaml 不再单独作 marker). _MIGRATE_MAP 保留 profile.yaml (迁移时还要拷); 只是 doctor 检查方式变严.

## 范围红线确认 (本期不做)

- [x] 不做 PyPI / GitHub Packages / release wheel installer
- [x] 不做 signing / hash integrity (manifest.integrity=null 留位, README 已加 caveat)
- [x] 不做 plugin marketplace 打包 (内部 git transport 先验)
- [x] 不做 methodology CLI (schema/template/validate 都 NOT_IMPLEMENTED + T-DIST-02 待办)
- [x] 不做第二份 methodology spec (D-097 自用为主)

## 询问 codex

1. force-include per-file 枚举 (B.0 design) 维护成本 P2 — 加 build_manifest_zones vs wheel_content CI 校验吗?
2. has_legacy_state 严判 (B.7) 是否会漏判? 如某 user 在 D-102.2 commit A 那个 0-diff plumbing 阶段就有部分迁移产物 — 现在 logs/ 已迁但 feedback_history 0 字节 + long_term_prefs 没 → has_legacy_state 返 False 也对 (本来就没真 legacy 内容).
3. ephemeral scope 隔离 (B.5c try/finally) 失败路径: subprocess 内 cmd_start 异常 → finally 恢复 env ✓; 但 TemporaryDirectory 删除 tmp 时 cmd_start 文件句柄未关 → tmp 可能残留. 现实测试无此情况, 但 Windows 上 tempfile 行为不同. P2 (主目标 macOS/Linux)?
4. install_root 智能探测在 PYTHONPATH 注入第二份 chisha 时可能错乱 — codex Round 1 已标 P3, 现状 OK.

## 总结

Sprint B 9 步全落, 跟修 1 次 (B.7), 跟修 1 次 (B.4 e2e fixture). 累计 4.3-5.0d 实际开发时间 (vs plan 估 4.8-8.7d, 实际 ≈下限). Sprint A R2 之后无重大返工.
