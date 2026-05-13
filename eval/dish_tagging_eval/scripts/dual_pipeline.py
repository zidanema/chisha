"""Dual-model golden set orchestration helper.

CLI 子命令(供 ralph-loop iteration 用):
  status        显示进度 (已完成 / 待跑 / failed)
  next-batch    输出下一个未完成 batch 的 5 dishes (JSON, 给 Opus S1)
  mark-done <batch_idx>   验证 final_batch_NNN.jsonl 通过校验后, 标记 progress.json
  merge         把所有 final_batch_*.jsonl 合并成 data/golden_set.jsonl

状态文件 (首次运行自动重建):
  scripts/_dual_state/batch_plan.json   34 batches 切片 (一次性生成)
  scripts/_dual_state/progress.json     运行时进度: {"completed":[1,2,...],"failed":[]}

数据文件:
  data/_dual_audit/final_batch_001.jsonl ... final_batch_034.jsonl  每 batch 5 条 final
  data/golden_set.jsonl   merge 后的最终 171 条

输出格式: stdout 输出可被 ralph iteration 解析的紧凑信息. 错误用 exit code != 0.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from _or_client import validate_record  # noqa: E402
from dish_inputs_v2 import all_inputs_v2  # noqa: E402


def anchor_violations(raw_name: str, exp: dict) -> list[str]:
    """对一条 expected 跑反直觉锚点自检, 返回违反列表(空 = 通过)."""
    v = []
    n = raw_name
    if any(k in n for k in ("红烧", "糖醋", "照烧", "京酱", "拔丝", "无锡酱")):
        if exp.get("sweet_sauce_level", 0) < 2:
            v.append(f"sweet_sauce_level<2 for '{n}'")
    if "蜜汁" in n or "蜂蜜" in n:
        if exp.get("sweet_sauce_level", 0) < 2:
            v.append(f"sweet_sauce_level<2 for honey '{n}'")
    if any(k in n for k in ("叉烧", "烧鸭", "烧鹅", "烧腊", "卤水", "白切鸡")) and "腊" not in n and "肠" not in n:
        if exp.get("processed_meat_flag") is True:
            v.append(f"processed_meat_flag=true for fresh-roast '{n}'")
    if any(k in n for k in ("腊肠", "培根", "午餐肉", "蟹柳", "火腿肠", "热狗")):
        if exp.get("processed_meat_flag") is False:
            v.append(f"processed_meat_flag=false for processed '{n}'")
    if any(k in n for k in ("套餐", "+饭", "+饮料", "+主食", "+汤", "+小菜", "拼盘")):
        if exp.get("dish_role") != "套餐":
            v.append(f"dish_role!=套餐 for '{n}'")
    if any(k in n for k in ("米粉", "河粉", "粿条", "肠粉", "螺蛳粉", "桂林米粉", "云南米线")):
        if exp.get("grain_type") != "白米":
            v.append(f"grain_type!=白米 for rice-noodle '{n}'")
    return v

STATE_DIR = SCRIPTS / "_dual_state"
AUDIT_DIR = ROOT / "data" / "_dual_audit"
BATCH_PLAN_PATH = STATE_DIR / "batch_plan.json"
PROGRESS_PATH = STATE_DIR / "progress.json"
GOLDEN_FINAL = ROOT / "data" / "golden_set.jsonl"
BATCH_SIZE = 5


def ensure_state_init() -> None:
    """First call: 生成 batch_plan.json (34 batches × 5 dishes) + progress.json (空)."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    if not BATCH_PLAN_PATH.exists():
        inputs = all_inputs_v2()  # 171 records
        batches = []
        for i in range(0, len(inputs), BATCH_SIZE):
            chunk = inputs[i:i + BATCH_SIZE]
            batches.append({
                "batch_idx": (i // BATCH_SIZE) + 1,
                "dish_ids": [d["dish_id"] for d in chunk],
                "dishes": chunk,
            })
        BATCH_PLAN_PATH.write_text(json.dumps(batches, ensure_ascii=False, indent=2))

    if not PROGRESS_PATH.exists():
        # Bootstrap: 把已经跑完的 5 个 batch (spike + 002-005) 标 completed
        # 检测 final_batch_*.jsonl 文件确定哪些已 done
        completed = []
        # spike 用 golden_set_dual.spike.jsonl, 对应 dish_ids = d010, d155, d159, d162, d169
        # 这 5 条分散在不同 batch_plan batches 里, 不算单个 batch
        # batch_002-005 对应 final_batch_002-005.jsonl
        for f in sorted(AUDIT_DIR.glob("final_batch_*.jsonl")):
            try:
                idx = int(f.stem.split("_")[-1])
                completed.append(idx)
            except ValueError:
                pass
        PROGRESS_PATH.write_text(json.dumps({
            "completed": completed,
            "failed": [],
            "spike_done": ["d010", "d155", "d159", "d162", "d169"],
        }, ensure_ascii=False, indent=2))


def load_progress() -> dict:
    ensure_state_init()
    return json.loads(PROGRESS_PATH.read_text())


def save_progress(p: dict) -> None:
    PROGRESS_PATH.write_text(json.dumps(p, ensure_ascii=False, indent=2))


def load_batch_plan() -> list[dict]:
    ensure_state_init()
    return json.loads(BATCH_PLAN_PATH.read_text())


def cmd_status() -> int:
    plan = load_batch_plan()
    prog = load_progress()
    completed = set(prog.get("completed", []))
    failed = set(prog.get("failed", []))
    total = len(plan)
    pending = [b["batch_idx"] for b in plan if b["batch_idx"] not in completed and b["batch_idx"] not in failed]
    spike = prog.get("spike_done", [])

    out = {
        "total_batches": total,
        "total_dishes": sum(len(b["dish_ids"]) for b in plan),
        "completed_batches": sorted(completed),
        "failed_batches": sorted(failed),
        "pending_batches_count": len(pending),
        "next_pending": pending[0] if pending else None,
        "spike_done_extra": spike,
        "is_complete": len(pending) == 0,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_next_batch() -> int:
    plan = load_batch_plan()
    prog = load_progress()
    completed = set(prog.get("completed", []))
    failed = set(prog.get("failed", []))

    for b in plan:
        if b["batch_idx"] in completed or b["batch_idx"] in failed:
            continue
        # Filter: skip dishes already in spike_done
        spike_done = set(prog.get("spike_done", []))
        kept_dishes = [d for d in b["dishes"] if d["dish_id"] not in spike_done]
        kept_ids = [d["dish_id"] for d in kept_dishes]

        if not kept_dishes:
            # 该 batch 所有 dish 都在 spike 完成了, 直接标 completed 推进
            completed.add(b["batch_idx"])
            prog["completed"] = sorted(completed)
            save_progress(prog)
            continue

        out = {
            "batch_idx": b["batch_idx"],
            "dish_ids": kept_ids,
            "dishes": kept_dishes,
            "expected_final_path": str(AUDIT_DIR / f"final_batch_{b['batch_idx']:03d}.jsonl"),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    print(json.dumps({"all_done": True}, ensure_ascii=False))
    return 0


def cmd_mark_done(batch_idx: int) -> int:
    plan = load_batch_plan()
    prog = load_progress()

    final_path = AUDIT_DIR / f"final_batch_{batch_idx:03d}.jsonl"
    if not final_path.exists():
        print(f"ERROR: {final_path} not found")
        return 1

    batch = next((b for b in plan if b["batch_idx"] == batch_idx), None)
    if not batch:
        print(f"ERROR: batch_idx {batch_idx} not in plan")
        return 1

    # Verify each record: schema + anchor_violations
    records = [json.loads(l) for l in final_path.open()]
    spike_done = set(prog.get("spike_done", []))
    expected_ids = [d for d in batch["dish_ids"] if d not in spike_done]

    rec_ids = [r["dish_id"] for r in records]
    if set(rec_ids) != set(expected_ids):
        print(f"ERROR: dish_ids mismatch. expected={expected_ids}, got={rec_ids}")
        return 2

    for r in records:
        ok, errs = validate_record(r["expected"])
        if not ok:
            print(f"ERROR: {r['dish_id']} schema invalid: {errs}")
            return 3
        vios = anchor_violations(r["input"]["raw_name"], r["expected"])
        if vios:
            print(f"ERROR: {r['dish_id']} anchor_violations: {vios}")
            return 4
        # consensus_status 必填且合法
        cs = r.get("consensus_status")
        if cs not in ("agree", "opus_wins", "codex_wins", "human_needed"):
            print(f"ERROR: {r['dish_id']} invalid consensus_status: {cs}")
            return 5

    completed = set(prog.get("completed", []))
    completed.add(batch_idx)
    prog["completed"] = sorted(completed)
    save_progress(prog)
    print(f"OK: batch {batch_idx} marked completed ({len(records)} records)")
    return 0


def cmd_merge() -> int:
    """合并所有 final + spike 到 golden_set.jsonl, 按 dish_id 升序."""
    plan = load_batch_plan()
    prog = load_progress()
    completed = set(prog.get("completed", []))

    all_records = []

    # Spike 5 条
    spike_path = ROOT / "data" / "golden_set_dual.spike.jsonl"
    if spike_path.exists():
        all_records.extend(json.loads(l) for l in spike_path.open())

    # Final batches
    for b in plan:
        if b["batch_idx"] not in completed:
            continue
        final_path = AUDIT_DIR / f"final_batch_{b['batch_idx']:03d}.jsonl"
        if not final_path.exists():
            continue
        all_records.extend(json.loads(l) for l in final_path.open())

    # 去重 + 排序
    by_id = {r["dish_id"]: r for r in all_records}
    ordered = sorted(by_id.values(), key=lambda r: (r["dish_id"][:1], int("".join(c for c in r["dish_id"][1:] if c.isdigit()) or "0"), r["dish_id"]))

    with GOLDEN_FINAL.open("w", encoding="utf-8") as f:
        for r in ordered:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"OK: merged {len(ordered)} records → {GOLDEN_FINAL}")

    # Stats
    from collections import Counter
    cs = Counter(r["consensus_status"] for r in ordered)
    nr = sum(1 for r in ordered if r.get("needs_review"))
    print(f"  consensus: {dict(cs)}")
    print(f"  needs_review: {nr}/{len(ordered)}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: dual_pipeline.py {status|next-batch|mark-done <idx>|merge}")
        return 1
    cmd = sys.argv[1]
    if cmd == "status":
        return cmd_status()
    if cmd == "next-batch":
        return cmd_next_batch()
    if cmd == "mark-done":
        if len(sys.argv) < 3:
            print("usage: dual_pipeline.py mark-done <batch_idx>")
            return 1
        return cmd_mark_done(int(sys.argv[2]))
    if cmd == "merge":
        return cmd_merge()
    print(f"unknown cmd: {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
