# OpenClaw Skill: chisha · 今天吃点啥

> V1: 工作日 11:25 / 18:00 主动推飞书卡片，3 选 1 决定吃啥。

## Skill 描述（OpenClaw 注册时填）

中午/晚上点外卖纠结时使用。基于哈佛餐盘弱约束（控油+有蔬菜+有蛋白）从用户当前办公区/家附近的商家中推荐 3 个组合，每个组合自带一句话理由。

触发关键词: 吃啥、吃什么、午餐、晚餐、点外卖、推荐外卖、外卖纠结。

## 调用方式

```python
from integrations.openclaw.skill import push_meal_recommendation

# 主动推送（cron 触发）
result = push_meal_recommendation(meal_type="lunch", chat_id="oc_xxx")

# 或环境变量驱动
# export OPENCLAW_PUSH_MODE=lark-cli LARK_CHAT_ID=oc_xxx
# python -m integrations.openclaw.skill lunch
```

返回 `{"out": <recommend_meal output §5.7>, "card": <feishu card json>, "status": "ok"}`。

## Cron 配置（OpenClaw 端）

```yaml
schedules:
  - name: chisha_lunch
    cron: "25 11 * * 1-5"   # 工作日 11:25
    skill: chisha.lunch
    args: {meal_type: lunch}
  - name: chisha_dinner
    cron: "0 18 * * 1-5"    # 工作日 18:00
    skill: chisha.dinner
    args: {meal_type: dinner}
```

> 周末不触发（profile.yaml 的 `meal_trigger_time.weekend: false` 仅作记录，
> 实际生效的是 OpenClaw cron 表达式 `1-5`）。

## 推送模式

`OPENCLAW_PUSH_MODE` 环境变量：

| 值 | 行为 | 适用场景 |
|---|---|---|
| `lark-cli` | 调用本机 `lark-cli im send` 推送到 `LARK_CHAT_ID` | 真实使用 |
| `stdout` | 打印卡片 JSON 到 stdout（默认） | 本地调试 |
| `noop` | 只生成卡片，不推送 | 单测 |

## 卡片交互

每个候选下方有【选这个】按钮。V1 阶段按钮只输出选择事件 (尚未接入 V2 的 `accept_recommendation` API)，
V2.0 接入后会自动写 `meal_log.jsonl` 并推反馈卡。

## 跳转 deeplink

V1 暂不附 deeplink（用户从 PRD 故事 1 描述自己跳到点评/美团）。V1.x 视使用反馈再加美团/点评 deeplink。

## V1 限制

- 不接收用户自然语言 refine（V2.1 才有）
- 不写反馈（V2.0 才有）
- 不做探索候选（V2.1 才有）
- chat_id 单聊场景，群聊场景未测
