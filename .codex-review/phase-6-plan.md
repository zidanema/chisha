# Phase 6 plan · 错误状态 + edge cases (chisha debug-ui)

## 4 个 prompt-required items + 2 carry-over

1. **L3 panel config_error 视觉**
   - 现状: status='config_error' 触发 StatusBadge orange 文字, 但 panel 整体看起来跟 OK 一样.
   - 改: 整个 PanelL3 加 .l3-config-error class → 橙边框 + 顶部 callout
     "profile_overrides JSON 解析失败 → L3 跳过". 已有 callout 给 fallback 用,
     复用同 callout 模式不同颜色.

2. **skipped 视觉**
   - 现状: status='skipped' 时 adapter 给空 IO viewer + StatusBadge gray.
   - 改: PanelL3 在 status='skipped' 时, 隐藏 io-viewer + meta-grid, 显示一个大的
     "L3 SKIPPED · LLM 关闭 / 跳过" callout. Final 用 L2 top 5 直出
     (backend 已经做了 fallback_rerank, final 5 仍有). 加注 "Final 来源:
     fallback rerank (L3 SKIPPED)".

3. **长文本溢出**
   - 现状: system_prompt ~6KB, user_message ~8KB. 浏览器 <pre> 直接渲染没问题
     (<30KB 都不卡).
   - 后端 user_message_full 可能 30-50KB+ (top60 全展开). 实测看再决定.
   - **Phase 6 不做虚拟滚动**, 但加: `.io-content { max-height: 600px; overflow: auto }`
     防内容把 panel 撑爆. Codex 同意 defer 虚拟滚动?

4. **空 session DAG / hint**
   - 现状: 第一次访问已经能看到 mock session (MOCK_SESSION). 不算空态.
   - 但用户 explicit 想要: backend offline 又没 cached session 时, DAG 节点显
     "—", 中间显 "click ▶ 触发首轮 to start".
   - 改: useSession 引入 `status === 'idle'` 且 no cached sessions → 渲 hint.
     现状 INITIAL_HISTORY_FALLBACK 总会有 mock row, 所以严格"空"很难触发.
     务实方案: 给 backend offline + 0 真实 history 时显示提示.

**carry-over (Codex flagged 但未做):**

5. **nutrition_profile 数字字段 cosmetic (Phase 4)**
   - 后端 oil_level/spicy_level/wetness 等是 0/1/2 数字, Trace panel `String(v)`
     渲染显示 "1". 加一个 numToLabel 映射:
     - oil/spicy/sweet/wetness: {0:'low', 1:'mid', 2:'high'} or similar
   - 不动后端 (会牵连主链路), 只在前端 adapter / Trace panel 里加 label hint.

6. **zone code 中文 mapping (Phase 4)**
   - 现状: backend 返回 zone='shenzhen-bay', UI 直显. 用户期望 "深圳湾办公区".
   - 加一个 ZONE_LABELS 字典 in `src/constants/zones.ts`, adapter 用它.

## 决策

- config_error / skipped panel 视觉用现有 CSS callout (red/orange) +
  整 panel 加 borderColor 微调, 不动 styles.css 太多.
- io-content 加 max-height 用 inline style 解决, 不动 styles.css.
- 空态 hint 用一个 panel-level Component (`<EmptyStateHint />`), 只在
  status==='idle' + history.length<=1 + history[0].id===MOCK 时渲染.
- ZONE_LABELS 字典先列 4-5 常见值 (shenzhen-bay/home/etc), fallback 用原 string.

## Codex 问

- io-content max-height: 600 合理还是 800?
- 空态 hint 应该挡住整个主视图 panels 还是只在 DAG 下方提示?
- numToLabel 映射 (0→low / 1→mid / 2→high) 这就是 chisha 后端的约定吗?
  Codex 跑 grep oil_level / wetness levels 在 chisha/score.py 验证.

中文 200-400 字 BLOCKER/FIX-NOW/DEFER。不要客套。
