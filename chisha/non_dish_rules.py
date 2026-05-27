"""非菜品识别 (collector 把餐具/包装/营销项当菜爬进来 → 打标前隔离).

只在 loader publish 路径调用 (chisha/loader.py: _build_dishes), 命中项 **non-blocking
隔离**: 不进 active dishes、不调 LLM、不进 conflicts 集 (不阻塞发布), 仅计数 + 报告.

精度第一 (宁可漏不可误杀真菜, 漏网的由 tag_via_api 单条具名隔离兜底):
- _NON_DISH_SUBSTR: 本质非食物词, 子串命中即判. 全量 23551 道实测含这些词的**全部**是非菜
  (餐具/一次性/保温袋...). 真菜名不含这些.
- _NON_DISH_EXACT: 裸器具词 (筷子/手套/勺子...) 子串不安全 (会误杀 "神枪手套餐"/"酱大骨配手套"
  /"筷子鸡"), 只在**去装饰后整名精确等于**时才判.

反例 (必须不命中, 见 tests/test_non_dish_rules.py): 神枪手套餐 / 配手套的菜 / 筷子鸡 /
餐包 / 叉烧 / 煲仔饭 / "牛腩...请备注" / "雪花肥牛一片（每单限购一份）".

已知接受的漏判: 强信号词只在括号注释里的非菜 (如 "加热盘（一次性）" 核心="加热盘") 会漏过
Layer 1 —— 这是精度优先的刻意取舍 (不为捞这类边角而冒误杀真菜的险), 漏网项由 tag_via_api
记录级隔离 (Layer 2) 兜底, 不进 active recall (D-101, Codex re-review Issue 2)。
"""
from __future__ import annotations

import re

# 本质非食物词 (子串命中即非菜). 不含 筷子/手套/勺子/叉子 等裸器具 (那些走 EXACT).
_NON_DISH_SUBSTR: tuple[str, ...] = (
    "餐具", "一次性", "保温袋", "餐巾纸", "湿巾", "打包袋",
)

# 裸器具/包装词: 子串会误杀真菜, 仅"去装饰后整名 == 词"才判非菜.
_NON_DISH_EXACT: frozenset[str] = frozenset({
    "勺子", "筷子", "手套", "牙签", "吸管", "叉子", "刀叉",
    "纸巾", "桌布", "手提袋", "塑料袋", "环保袋", "餐巾",
})

# 去装饰: 空白 (含 unicode 空格)、括号内修饰、拉丁字母、尾部计数 → 留核心名做 EXACT 比对.
_WS = re.compile(r"\s+")
_BRACKET = re.compile(r"[【\[(（].*?[】\])）]")
_LATIN = re.compile(r"[A-Za-z]+")
_COUNT = re.compile(r"\d+\s*(双|个|份|套|根|片|串|包)?")


def _strip_decorations(name: str) -> str:
    s = _BRACKET.sub("", name)
    s = _LATIN.sub("", s)
    s = _COUNT.sub("", s)
    s = _WS.sub("", s)
    return s.strip("·-—~！!。，,、/ ")


def is_non_dish(raw_name: str) -> bool:
    """采集端菜名是否实为非菜品 (餐具/包装/裸器具). 精度优先, 漏报可接受.

    子串与 EXACT 都打在**去装饰核心**上 (先剥括号注释/拉丁/计数): 防真菜的括号备注
    误杀 —— "双人套餐（含一次性餐具）" 核心是 "双人套餐", 不含强信号词 → 不命中。
    """
    if not raw_name:
        return False
    core = _strip_decorations(raw_name)
    if any(tok in core for tok in _NON_DISH_SUBSTR):
        return True
    return core in _NON_DISH_EXACT
