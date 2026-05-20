// labels.ts — single source of truth for backend enum → 中文 UI mapping.
// Keep API parity with the prototype's window.LABELS (DESIGN_NOTES §3).
// All UI components MUST go through `LABELS` rather than rendering raw enum values.

import type { Mood, MoodResponse, MealType, ZoneId, IngredientKind } from "./types";

interface BannerText {
  before: string;
  name: string;
  after: string;
}

export const LABELS = {
  meal: { lunch: "午餐", dinner: "晚餐" } as Record<MealType, string>,

  // D-071: mood picker 已下线, 仅保留 neutral chip. 历史标签 (清淡/解馋/轻食/想喝汤/
  // 低碳水) 走 refine 文本关键词通道, 不再以 chip 形式 UI 展示, 但旧 history 数据
  // 仍可能带历史 mood key — 这里给出兜底标签防 undefined.
  mood: {
    neutral: "随便",
    want_clean: "清淡",
    want_indulgent: "解馋",
    want_light: "轻食",
    want_soup: "想喝汤",
    low_carb: "低碳水",
  } as Record<MoodResponse, string>,

  moodList: ["neutral"] as Mood[],

  zone: {
    "shenzhen-bay": "深圳湾科技园",
    "home": "家附近",
    "futian-cbd": "福田 CBD",
    "beijing-zgc": "北京中关村",
    "shanghai-xhh": "上海徐汇湾",
    other: "其它",
  } as Record<ZoneId, string>,

  ingredientColor: {
    红肉: "oklch(0.62 0.15 25)",
    白肉: "oklch(0.70 0.10 60)",
    海鲜: "oklch(0.63 0.11 210)",
    蛋: "oklch(0.72 0.12 90)",
    豆制品: "oklch(0.65 0.09 130)",
    纯素: "oklch(0.62 0.12 145)",
    主食: "oklch(0.60 0.04 75)",
  } as Record<IngredientKind, string>,

  refineChips: [
    "想吃辣的",
    "换日料",
    "来份烧烤",
    "想吃牛肉",
    "来盖饭",
    "换粤菜",
  ],

  refineInputPlaceholders: [
    "或者，告诉我你今天想要什么...",
    "想吃辣的，或者今天就想要带汤水的...",
    "换日式定食",
    "不想吃面，给我个有锅气的",
  ],

  skipReasons: [
    { id: "cafeteria", label: "食堂" },
    { id: "brought", label: "自带饭" },
    { id: "outside", label: "在外吃" },
    { id: "social", label: "和同事一起" },
    { id: "none_fit", label: "都没看上" },
    { id: "not_hungry", label: "不饿" },
  ] as { id: Exclude<import("./types").SkipReason, null>; label: string }[],

  ui: {
    homeTitle: "今天吃点啥",
    navPrefer: "偏好",
    navHistory: "历史",
    navFeedback: "反馈",
    navBack: "回主页",

    mealLunch: "午餐",
    mealDinner: "晚餐",
    regen: "换一组",
    loadingHint: "正在为你挑选...",
    loadingHintLong: "15-60 秒不等",

    homeSecTitle: "今天的推荐",
    expandAlts: (n: number) => `${n} 个备选 ▽`,
    collapseAlts: "收起备选 △",
    pickThis: "就这个",
    pickThisAlt: "选这个",
    picked: "已选",
    pickedTitle: "已记录你的选择",
    pickedActHint: "打开美团 / 点评，搜店名下单 →",
    pickedFbHint: "饭后回主页填一下反馈 →",
    pickChange: "改主意",
    copyName: "复制店名",
    copyDone: "已复制",
    detail: "查看详情",

    refineTitle: "不喜欢？换个口味试试",
    refineCustomTitle: "或者写一句",
    refineSubmit: "换一组",
    refineHistory: "刚才你试过这几次：",

    bannerText: (name: string): BannerText => ({
      before: "中午吃的",
      name,
      after: "怎么样？",
    }),
    bannerCta: "5 秒反馈一下 →",
    bannerDismiss: "关闭提醒",
    bannerStackMore: (n: number) => `还有 ${n} 餐没反馈`,
    bannerStackGo: "去反馈中心 →",
    bannerSnooze: "以后再说",
    bannerStop: "这餐别催了",
    bannerOpenMenu: "更多",

    fbBackToHome: "回主页",
    fbBackToInbox: "反馈中心",
    fbPickedHint: "你当时点的是",
    fbNoPickHint: "没记录到你的选择 — 直接选下面任意一项",
    fbNotEaten: "都没吃这几个",
    fbNote: "备注（可选）",
    fbNotePlaceholder: "比如：辣度刚好、米饭硬了点...",
    fbDone: "已记录，明天见 →",
    fbEmpty: "没有待反馈的推荐",
    fbEmptyAction: "回主页 →",
    fbSubmit: "完成",

    // ── 表单 · 渐进披露 E (D-062~063) ──────────────────────────
    fbAQuestion: "这顿怎么样？",
    fbARatingBad: "难吃",
    fbARatingOk: "普通",
    fbARatingGood: "好吃",
    fbANotEaten: "其实没吃这个 →",
    fbEExpand: "多说一点（送系统一个礼物）▽",
    fbECollapse: "收起 △",
    fbEColPrediction: "当时预估",
    fbEColReality: "你实际",
    fbEDim: {
      reason:   { label: "推荐理由", opts: ["正中", "还行", "没感觉"] },
      fullness: { label: "饱腹感",   opts: ["不够", "刚好", "太多"] },
      oil:      { label: "油腻感",   opts: ["太油", "刚好", "太淡"] },
      repeat:   { label: "下次还点", opts: ["不会", "偶尔", "会"] },
    },

    // ── Detail view (D-066/065) ─────────────────────────────────
    fbDetailTitle: "反馈已记录",
    fbDetailSubmittedAt: (ago: string) => `${ago}提交`,
    fbDetailLocked: "已封存 · 不可修改，但可以追加备注",
    fbDetailOriginalNote: "当时备注",
    fbDetailTimeline: "之后补充",
    fbDetailAppendTitle: "想补充点什么？",
    fbDetailAppendPlaceholder:
      "比如：第二天回想，胃确实有点重；下次还会再点但要备注少油...",
    fbDetailAppendSubmit: "追加",
    fbDetailRating: "整体好吃度",
    fbDetailNoRating: "没打整体分",
    fbDetailNotEaten: "标记为「没吃这几个」",
    fbDetailJumpHome: "回主页 →",

    // ── Inbox /feedback (D-058) ─────────────────────────────────
    inboxTitle: "反馈",
    inboxSubtitle: "饭后回来打个分，下次推得更准",
    inboxPending: "待反馈",
    inboxSnoozed: "暂缓",
    inboxDone: "已反馈",
    inboxEmpty: "都跟进完了 — 收工",
    inboxEmptyHint: "下次点完外卖，这里会自动列出",
    inboxBackHome: "回主页看推荐 →",
    inboxPendingHint: (n: number) => `${n} 餐还没打分`,
    inboxRowOpen: "去反馈 →",
    inboxRowSnoozed: "暂缓",
    inboxAgo: (mins: number) =>
      mins < 60
        ? `${mins} 分钟前`
        : mins < 60 * 24
          ? `${Math.floor(mins / 60)} 小时前`
          : `${Math.floor(mins / 60 / 24)} 天前`,
    inboxFedChip: (rating: -1 | 0 | 1 | null) =>
      rating === 1 ? "👍 好吃" : rating === 0 ? "😐 普通" : rating === -1 ? "👎 难吃" : "—",

    profileTitle: "偏好",
    profileEdit: "编辑",
    profileSave: "保存修改",
    profileCancel: "取消",
    profileReset: "恢复默认",
    profileUndo: "撤销",
    profileLastMod: "最后修改",
    profileReadHint: "当前偏好预览",
    profileEditHint: "未保存修改时左侧有红点提示",

    detailDishes: "单菜清单",
    detailMatch: "匹配度",
    detailRisks: "风险",

    skipCta: "这顿吃别的，跳过 →",
    skipPromptT: "为什么跳过？",
    skipPromptHint: "帮系统下次别推这类",
    skipNoReason: "不说原因 · 跳过 →",
    skipDone: "本餐已跳过",
    skipDoneByeline: "明天见 →",
    skipUndo: "撤销，重新看推荐",
    skippedToast: "已记录，本餐不再提醒",

    version: "v0.1",
    versionTip: "chisha v1 · localhost · D-051 build",

    unknownRoute: "未知路由",
    backHome: "回主页",

    pickedRank: (r: number) => `吃了 #${r}`,
    notEatenShort: "都没吃",
    historyUnfedChip: "未反馈",
    historyFedChip: "已反馈",
    historyHintClickable: "点行可打分 / 看详情",
  },
};

export type LabelsShape = typeof LABELS;
