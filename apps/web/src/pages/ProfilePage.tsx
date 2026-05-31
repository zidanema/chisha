import { useEffect, useMemo, useState } from "react";
import { LABELS } from "@/lib/labels";
import { api } from "@/lib/api";
import { useChisha } from "@/lib/useChishaState";
import { PROFILE_DEFAULTS } from "@/lib/profileDefaults";
import type { Profile } from "@/lib/types";
import { toYaml } from "@/lib/yaml";

import { PageShell, FooterBar } from "@/components/PageShell";
import { YamlViewer } from "@/components/YamlViewer";
import {
  ProfileBasicsGroup,
  ProfileDeliveryGroup,
  ProfileLLMGroup,
  ProfileMealTimeGroup,
  ProfilePlateRuleGroup,
  ProfilePriceGroup,
  ProfileTasteGroup,
} from "@/components/profile/ProfileGroups";

// D-055: 默认 = 只读 YAML。点编辑切表单；保存后回只读视图。

export function ProfilePage() {
  const { showToast } = useChisha();
  const [profile, setProfile] = useState<Profile>(PROFILE_DEFAULTS);
  const [mode, setMode] = useState<"read" | "edit">("read");
  const [local, setLocal] = useState<Profile>(profile);

  useEffect(() => {
    void api.getProfile().then((p) => {
      setProfile(p);
      setLocal(p);
    });
  }, []);
  useEffect(() => setLocal(profile), [profile]);

  const dirty = useMemo(
    () => JSON.stringify(local) !== JSON.stringify(profile),
    [local, profile]
  );
  const yamlSource = useMemo(() => toYaml(profile), [profile]);

  function setPath(path: string, value: unknown) {
    setLocal((p) => {
      const next = JSON.parse(JSON.stringify(p));
      const parts = path.split(".");
      let o: Record<string, unknown> = next;
      for (let i = 0; i < parts.length - 1; i++) {
        o = o[parts[i]] as Record<string, unknown>;
      }
      o[parts[parts.length - 1]] = value;
      return next;
    });
  }
  async function save() {
    await api.putProfile(local);
    setProfile(local);
    showToast("已保存 → profile.yaml", "good");
    setMode("read");
  }
  function cancel() {
    setLocal(profile);
    setMode("read");
  }
  function reset() {
    setLocal(PROFILE_DEFAULTS);
  }

  if (mode === "read") {
    const lunchZone =
      LABELS.zone[profile.basics?.zones?.lunch] || profile.basics?.zones?.lunch;
    return (
      <PageShell>
        <div className="mt-5 mb-4 flex items-baseline gap-3">
          <h1 className="text-[18px] font-semibold tracking-tight">
            {LABELS.ui.profileTitle}
          </h1>
          <span className="text-[12px] text-[color:var(--muted)]">
            当前区域：{lunchZone}
          </span>
          <button
            onClick={() => setMode("edit")}
            className="ml-auto text-[13px] px-3 py-1.5 rounded-md border border-[color:var(--border)] hover:border-[color:var(--fg)] inline-flex items-center gap-1.5"
          >
            <span aria-hidden="true">✎</span>
            {LABELS.ui.profileEdit}
          </button>
        </div>

        <p className="text-[12.5px] text-[color:var(--muted)] mb-3">
          {LABELS.ui.profileReadHint}
        </p>

        <YamlViewer source={yamlSource} />

        <FooterBar />
      </PageShell>
    );
  }

  // ── Edit mode ──────────────────────────────────────────────────────────────
  return (
    <PageShell>
      <div className="sticky top-12 z-20 -mx-6 px-6 py-3 bg-[color:var(--bg)]/95 backdrop-blur border-b border-[color:var(--border)] flex items-baseline gap-3">
        <h1 className="text-[17px] font-semibold tracking-tight">
          {LABELS.ui.profileTitle} · 编辑
        </h1>
        {dirty && (
          <span
            className="w-2 h-2 rounded-full bg-[color:var(--bad)] self-center"
            aria-label="未保存"
          />
        )}
        <span className="text-[11px] text-[color:var(--muted)]">
          {dirty ? "未保存修改" : "已同步"}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={cancel}
            className="text-[12.5px] px-3 py-1.5 rounded-md border border-[color:var(--border)]"
          >
            ← {LABELS.ui.profileCancel}
          </button>
          <button
            onClick={() => setLocal(profile)}
            disabled={!dirty}
            className="text-[12.5px] px-3 py-1.5 rounded-md border border-[color:var(--border)] disabled:opacity-40"
          >
            {LABELS.ui.profileUndo}
          </button>
          <button
            onClick={reset}
            className="text-[12.5px] px-3 py-1.5 rounded-md border border-[color:var(--border)]"
          >
            {LABELS.ui.profileReset}
          </button>
          <button
            onClick={save}
            disabled={!dirty}
            className="text-[13px] px-3 py-1.5 rounded-md font-medium disabled:opacity-40"
            style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
          >
            {LABELS.ui.profileSave}
          </button>
        </div>
      </div>

      <p className="mt-4 mb-5 text-[12.5px] text-[color:var(--muted)] leading-relaxed">
        弱约束是软门槛，强约束（hard_max_*）是硬过滤。 最关键的字段：
        <span className="text-[color:var(--fg)]">口味描述</span>（LLM 主要靠它判断口味契合）。
      </p>

      <div className="space-y-4">
        <ProfileBasicsGroup local={local} setPath={setPath} />
        <ProfilePlateRuleGroup local={local} setPath={setPath} />
        <ProfileTasteGroup local={local} setPath={setPath} />
        <ProfileDeliveryGroup local={local} setPath={setPath} />
        <ProfilePriceGroup local={local} setPath={setPath} />
        <ProfileMealTimeGroup local={local} setPath={setPath} />
        <ProfileLLMGroup local={local} setPath={setPath} />
      </div>

      <FooterBar />
    </PageShell>
  );
}
