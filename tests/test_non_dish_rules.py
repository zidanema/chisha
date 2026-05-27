"""非菜品识别规则: 正例命中 + 真菜负例不误杀 (Codex 设计 review 点名的雷区)."""
import pytest

from chisha.non_dish_rules import is_non_dish

# 真非菜品 → 必须命中
NON_DISH = [
    "需要餐具",
    "不需要餐具（不给筷子）",
    "一次性餐具（每单仅需点一份）",
    "需要一次性叉勺(每单仅需点一份)",
    "四件套餐具包 （按需选购，爱护环境）",
    "和府餐具包",
    "一次性手套(2 双)",
    "一次性筷子",
    "保温袋一个",
    "【必选】保温袋 1 个，多拍不送",
    "纸巾",
    "纸巾 Handkerchief",
    "勺子 Spoon",
    "牙签",
]

# 真菜 / 真食物 → 必须不命中 (broad 子串误杀雷区)
REAL_DISH = [
    "神枪手套餐",                       # "手套餐" 套餐, 含"手套"
    "果木烟熏鸡胸超级碗神枪手套餐",
    "番茄炒蛋+口水鸡+糙米饭【神枪手套餐】",
    "酱大骨（1 个） 配手套【大口吃肉】",  # 配手套的真菜
    "酱骨架【老卤熬制】配手套",
    "筷子鸡",                            # Codex 点名
    "餐包",                              # dinner roll
    "黄油餐包",
    "蜜汁叉烧",                          # 含"叉"
    "煲仔饭",
    "牛腩不吃肥的请备注一下",            # 真菜 + 备注
    "雪花肥牛一片（每单限购一份）",      # 真菜 + 每单限购
    "干炒牛河（默认不辣，如需加辣请备注）",
    "芜湖刨凉粉（辣，免辣要备注）",
    "白糖包（每单限点两份，多点不送哦）",
    # 真套餐, 强信号词只在括号备注里 → 去核心后不命中 (Codex P2 误杀雷区)
    "双人套餐（含一次性餐具）",
    "烤鸡套餐（送餐具）",
    "豪华午餐（赠一次性手套）",
]


@pytest.mark.parametrize("name", NON_DISH)
def test_non_dish_caught(name):
    assert is_non_dish(name), f"漏判非菜品: {name!r}"


@pytest.mark.parametrize("name", REAL_DISH)
def test_real_dish_not_caught(name):
    assert not is_non_dish(name), f"误杀真菜: {name!r}"


def test_empty():
    assert not is_non_dish("")
