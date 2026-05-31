import { LABELS } from "@/lib/labels";
import type { Profile } from "@/lib/types";
import { ChipListEditor } from "@/components/profile/ChipListEditor";
import {
  Field,
  FieldGroup,
  NumberInput,
  Select,
  Slider,
  TextInput,
  Toggle,
} from "@/components/profile/Inputs";

type SetPath = (path: string, value: unknown) => void;

type ProfileGroupProps = {
  local: Profile;
  setPath: SetPath;
};

const ZONE_OPTIONS = (Object.entries(LABELS.zone) as [string, string][]).map(
  ([id, label]) => ({ id, label }),
);

export function ProfileBasicsGroup({ local, setPath }: ProfileGroupProps) {
  return (
    <FieldGroup title="基本信息" idx="01">
      <div className="grid grid-cols-2 gap-4">
        <Field label="name">
          <TextInput value={local.basics.name} onChange={(v) => setPath("basics.name", v)} />
        </Field>
        <Field label="city">
          <TextInput value={local.basics.city} onChange={(v) => setPath("basics.city", v)} />
        </Field>
      </div>
      <Field label="goal" hint="健康/训练目标，自然语言">
        <textarea
          rows={2}
          value={local.basics.goal}
          onChange={(e) => setPath("basics.goal", e.target.value)}
          className="w-full bg-transparent rounded-md border border-[color:var(--border)] p-2 text-[13px] focus:outline-none focus:border-[color:var(--fg)] resize-none leading-relaxed"
        />
      </Field>
      <div className="grid grid-cols-2 gap-4">
        <Field label="zones.lunch">
          <Select value={local.basics.zones.lunch} onChange={(v) => setPath("basics.zones.lunch", v)} options={ZONE_OPTIONS} />
        </Field>
        <Field label="zones.dinner">
          <Select value={local.basics.zones.dinner} onChange={(v) => setPath("basics.zones.dinner", v)} options={ZONE_OPTIONS} />
        </Field>
      </div>
    </FieldGroup>
  );
}

export function ProfilePlateRuleGroup({ local, setPath }: ProfileGroupProps) {
  return (
    <FieldGroup title="弱约束·三件套" idx="02" hint="哈佛餐盘法的软门槛">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="must_have_vegetable">
          <Toggle
            value={local.plate_rule.must_have_vegetable}
            onChange={(v) => setPath("plate_rule.must_have_vegetable", v)}
            label={local.plate_rule.must_have_vegetable ? "开" : "关"}
          />
        </Field>
        <Field label="min_vegetable_dishes" hint="最少蔬菜道数">
          <NumberInput value={local.plate_rule.min_vegetable_dishes} min={0} max={3} onChange={(v) => setPath("plate_rule.min_vegetable_dishes", v)} unit="道" />
        </Field>
        <Field label="min_protein_g" hint="每顿最少蛋白">
          <NumberInput value={local.plate_rule.min_protein_g} min={0} max={120} step={5} onChange={(v) => setPath("plate_rule.min_protein_g", v)} unit="g" />
        </Field>
        <Field label="prefer_oil_level_at_most" hint="偏好上限 1-5">
          <Slider value={local.plate_rule.prefer_oil_level_at_most} min={1} max={5} step={1} onChange={(v) => setPath("plate_rule.prefer_oil_level_at_most", v)} />
        </Field>
        <Field label="hard_max_oil_level" hint="硬过滤上限 1-5">
          <Slider value={local.plate_rule.hard_max_oil_level} min={1} max={5} step={1} onChange={(v) => setPath("plate_rule.hard_max_oil_level", v)} />
        </Field>
      </div>
    </FieldGroup>
  );
}

export function ProfileTasteGroup({ local, setPath }: ProfileGroupProps) {
  return (
    <FieldGroup title="口味偏好" idx="03" hint="最重要 · LLM 主要靠这一段">
      <Field label="taste_description" hint="自然语言长描述 · 至少 10 行">
        <textarea
          rows={14}
          value={local.taste_description}
          onChange={(e) => setPath("taste_description", e.target.value)}
          className="w-full bg-[color:var(--bg)] rounded-md border border-[color:var(--border)] p-3 text-[12.5px] font-mono focus:outline-none focus:border-[color:var(--fg)] resize-y leading-relaxed"
          style={{ minHeight: "220px" }}
        />
        <div className="text-[10.5px] text-[color:var(--muted)] font-mono mt-1 tabular-nums">
          {local.taste_description.length} 字符 · {local.taste_description.split("\n").length} 行
        </div>
      </Field>
      <div className="grid grid-cols-1 gap-4">
        <Field label="liked_cuisines">
          <ChipListEditor value={local.preferences.liked_cuisines} onChange={(v) => setPath("preferences.liked_cuisines", v)} placeholder="+ 添加菜系" />
        </Field>
        <Field label="disliked_cuisines">
          <ChipListEditor value={local.preferences.disliked_cuisines} onChange={(v) => setPath("preferences.disliked_cuisines", v)} placeholder="+ 不太喜欢的菜系" />
        </Field>
        <Field label="banned_cuisines" hint="硬过滤">
          <ChipListEditor value={local.preferences.banned_cuisines} onChange={(v) => setPath("preferences.banned_cuisines", v)} placeholder="+ 完全不接受" tone="bad" />
        </Field>
        <Field label="avoid_dishes" hint="按菜名忌口">
          <ChipListEditor value={local.preferences.avoid_dishes} onChange={(v) => setPath("preferences.avoid_dishes", v)} placeholder="例：香菜、肥肠" tone="bad" />
        </Field>
        <Field label="avoid_main_ingredients">
          <ChipListEditor value={local.preferences.avoid_main_ingredients} onChange={(v) => setPath("preferences.avoid_main_ingredients", v)} placeholder="例：内脏、芹菜" />
        </Field>
        <Field label="avoid_cooking_methods">
          <ChipListEditor value={local.preferences.avoid_cooking_methods} onChange={(v) => setPath("preferences.avoid_cooking_methods", v)} placeholder="例：油炸、煎" />
        </Field>
        <Field label="avoid_restaurants">
          <ChipListEditor value={local.preferences.avoid_restaurants} onChange={(v) => setPath("preferences.avoid_restaurants", v)} placeholder="按商家名" />
        </Field>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="spicy_tolerance" hint="0=不辣 · 1=微 · 2=中 · 3=重">
          <Slider value={local.preferences.spicy_tolerance} min={0} max={3} step={1} onChange={(v) => setPath("preferences.spicy_tolerance", v)} />
        </Field>
        <Field label="banned_sweet_sauce_level_3" hint="禁糖醋/蜜汁/照烧">
          <Toggle value={local.preferences.banned_sweet_sauce_level_3} onChange={(v) => setPath("preferences.banned_sweet_sauce_level_3", v)} label={local.preferences.banned_sweet_sauce_level_3 ? "禁" : "允许"} />
        </Field>
        <Field label="banned_processed_meat" hint="禁香肠/培根/午餐肉">
          <Toggle value={local.preferences.banned_processed_meat} onChange={(v) => setPath("preferences.banned_processed_meat", v)} label={local.preferences.banned_processed_meat ? "禁" : "允许"} />
        </Field>
      </div>
    </FieldGroup>
  );
}

export function ProfileDeliveryGroup({ local, setPath }: ProfileGroupProps) {
  return (
    <FieldGroup title="履约约束" idx="04">
      <div className="grid grid-cols-2 gap-4">
        <Field label="hard_max_eta_min" hint="超时硬过滤">
          <NumberInput value={local.delivery_constraints.hard_max_eta_min} min={10} max={90} onChange={(v) => setPath("delivery_constraints.hard_max_eta_min", v)} unit="min" />
        </Field>
        <Field label="prefer_max_eta_min" hint="软偏好">
          <NumberInput value={local.delivery_constraints.prefer_max_eta_min} min={10} max={90} onChange={(v) => setPath("delivery_constraints.prefer_max_eta_min", v)} unit="min" />
        </Field>
      </div>
    </FieldGroup>
  );
}

export function ProfilePriceGroup({ local, setPath }: ProfileGroupProps) {
  return (
    <FieldGroup title="价格约束" idx="05">
      <div className="grid grid-cols-2 gap-4">
        <Field label="hard_max_lunch">
          <NumberInput value={local.price_range.hard_max_lunch} min={20} max={300} onChange={(v) => setPath("price_range.hard_max_lunch", v)} unit="¥" />
        </Field>
        <Field label="hard_max_dinner">
          <NumberInput value={local.price_range.hard_max_dinner} min={20} max={300} onChange={(v) => setPath("price_range.hard_max_dinner", v)} unit="¥" />
        </Field>
        <Field label="prefer_max_lunch">
          <NumberInput value={local.price_range.prefer_max_lunch} min={20} max={300} onChange={(v) => setPath("price_range.prefer_max_lunch", v)} unit="¥" />
        </Field>
        <Field label="prefer_max_dinner">
          <NumberInput value={local.price_range.prefer_max_dinner} min={20} max={300} onChange={(v) => setPath("price_range.prefer_max_dinner", v)} unit="¥" />
        </Field>
      </div>
    </FieldGroup>
  );
}

export function ProfileMealTimeGroup({ local, setPath }: ProfileGroupProps) {
  return (
    <FieldGroup title="触发时间" idx="06" hint="到点 macOS 拉起本页">
      <div className="grid grid-cols-3 gap-4">
        <Field label="lunch">
          <input type="time" value={local.meal_trigger_time.lunch} onChange={(e) => setPath("meal_trigger_time.lunch", e.target.value)} className="w-full bg-transparent rounded-md border border-[color:var(--border)] py-1.5 px-2.5 text-[13px] font-mono tabular-nums focus:outline-none focus:border-[color:var(--fg)]" />
        </Field>
        <Field label="dinner">
          <input type="time" value={local.meal_trigger_time.dinner} onChange={(e) => setPath("meal_trigger_time.dinner", e.target.value)} className="w-full bg-transparent rounded-md border border-[color:var(--border)] py-1.5 px-2.5 text-[13px] font-mono tabular-nums focus:outline-none focus:border-[color:var(--fg)]" />
        </Field>
        <Field label="weekend" hint="周末是否触发">
          <Toggle value={local.meal_trigger_time.weekend} onChange={(v) => setPath("meal_trigger_time.weekend", v)} label={local.meal_trigger_time.weekend ? "开" : "关"} />
        </Field>
      </div>
    </FieldGroup>
  );
}

export function ProfileLLMGroup({ local, setPath }: ProfileGroupProps) {
  return (
    <FieldGroup title="LLM / 高级" idx="07" defaultOpen={false}>
      <div className="grid grid-cols-2 gap-4">
        <Field label="provider">
          <Select<typeof local.llm.provider> value={local.llm.provider} onChange={(v) => setPath("llm.provider", v)} options={["auto", "claude_code_cli", "anthropic", "openrouter"]} />
        </Field>
        <Field label="model.claude_code_cli">
          <TextInput mono value={local.llm.model.claude_code_cli} onChange={(v) => setPath("llm.model.claude_code_cli", v)} />
        </Field>
        <Field label="model.anthropic">
          <TextInput mono value={local.llm.model.anthropic} onChange={(v) => setPath("llm.model.anthropic", v)} />
        </Field>
        <Field label="model.openrouter">
          <TextInput mono value={local.llm.model.openrouter} onChange={(v) => setPath("llm.model.openrouter", v)} />
        </Field>
      </div>
    </FieldGroup>
  );
}
