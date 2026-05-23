# prompts/ DEV NOTES (给改 prompt 的 agent)

> 这个文件**不被任何 Python 加载**, 不进 token bill。改 prompt 前 grep 这里看锚点约束 + 跨文件耦合。

## rerank_system.md 锚点 (改后必跑 tests/test_rerank.py)

`chisha/rerank.py:_patch_system_prompt_for_cli` 用字面匹配把 tool_use 路径的 system_prompt patch 成 CLI no-tool 版本。两个锚点不能动:

- 顶级 `# 输出方式` 标题 = CLI no-tool 路径替换段锚点 (整段被替换)
- 文末含 `select_top_candidates` 和 `现在等待` 的那行 = 末尾指令替换锚点 (整行被替换)

改这两处需同步:
- `chisha/rerank.py` 的 `_patch_system_prompt_for_cli` 匹配逻辑 + `_CLI_OUTPUT_SECTION` + `_CLI_TAIL_INSTRUCTION` 常量
- `tests/test_rerank.py` 相关 patch 锚点测试

锚点缺失时 `_patch_system_prompt_for_cli` 显式 raise ValueError (D-048), 不会静默 fallback。

## parse_refine_intent_v2.md 锚点

待补 (V1 退役 + Step 2 refine 部分启动时落)。
