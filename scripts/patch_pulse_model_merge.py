#!/usr/bin/env python3
"""Restore the model-merge statistics feature (and the statistics memory budget)
on top of upstream Antigrative Dashboard.

1) MODEL MERGE
   Upstream formats the model display name (context.mjs `formatModelName`) but
   the statistics aggregation still keys every series by the raw host model id,
   so host placeholder ids (MODEL_PLACEHOLDER_M318 / M319 / M320 ...) and tier
   variants ("gemini-3.8-flash-tiered", "Claude Sonnet 4.6 (Thinking)", ...)
   show up as separate series instead of one series per model family.

   This patch merges the model name at the *source* (usage.mjs row creation),
   so the whole chain - aggregation, disk worker, panel UI, inline widget usage
   view - aggregates per model family. The *current request* display (inline
   status bar) is untouched: there the tier (High/Medium/Low) still matters.

2) STATISTICS BUDGET
   Upstream keeps only 8 MiB of a trajectory payload. Long conversations
   (tens of thousands of steps) exceed it by a few bytes and the collection
   ends in state "limited" / code "budget-exceeded" - the dashboard then shows
   the statistics as restricted instead of complete. Raising the retained
   budget to 32 MiB lets those conversations finish, and the background worker
   heap is raised to match.

Idempotent: re-running is a no-op once the markers are present.

Usage:
    python patch_pulse_model_merge.py [plugin_dir]
"""
import re
import sys
from pathlib import Path

MARKER = "PULSE_MODEL_MERGE_V1"
MODULE = "model-merge.mjs"
BUDGET = 32 * 1024 * 1024

HELPER_MODULE = """// {marker}
// Host model ids arrive in many shapes: placeholder ids
// (MODEL_PLACEHOLDER_M318), slug ids (gemini-3.8-flash-tiered), display names
// with a tier suffix (Claude Sonnet 4.6 (Thinking)). Statistics must aggregate
// one series per model family, so normalise every shape to the family name.
// Unknown models are left untouched on purpose.
import {formatModelName} from './context.mjs';

const clean=value=>String(value||'Unknown').replace(/[\\x00-\\x1f\\x7f]/g,'').slice(0,120);

const TIER=/\\s*\\((?:X?High|Medium|Low|Thinking|Preview)\\)\\s*$/i;

const FAMILIES=[
  [/^gemini[\\s._-]*3[\\s._-]*8[\\s._-]*flash/i,'Gemini 3.8 Flash'],
  [/^gemini[\\s._-]*3[\\s._-]*6[\\s._-]*flash/i,'Gemini 3.6 Flash'],
  [/^gemini[\\s._-]*3[\\s._-]*1[\\s._-]*pro/i,'Gemini 3.1 Pro'],
  [/^gemini[\\s._-]*4[\\s._-]*argon/i,'Gemini 4 Argon'],
  [/^gemini[\\s._-]*4[\\s._-]*hydrogen/i,'Gemini 4 Hydrogen'],
  [/^gemini[\\s._-]*4[\\s._-]*neon/i,'Gemini 4 Neon'],
  [/^claude[\\s._-]*sonnet[\\s._-]*4[\\s._-]*6/i,'Claude Sonnet 4.6'],
  [/^claude[\\s._-]*sonnet[\\s._-]*5[\\s._-]*5/i,'Claude Sonnet 5.5'],
  [/^claude[\\s._-]*opus[\\s._-]*4[\\s._-]*6/i,'Claude Opus 4.6'],
  [/^claude[\\s._-]*opus[\\s._-]*5[\\s._-]*5/i,'Claude Opus 5.5'],
  [/^gpt[\\s._-]*oss[\\s._-]*120b/i,'GPT-OSS 120B'],
];

export function mergedModelName(raw){
  const cleaned=clean(raw);
  const display=formatModelName(cleaned);
  let base=(display||cleaned).replace(TIER,'').trim();
  for(const [pattern,name] of FAMILIES){
    if(pattern.test(base))return name;
  }
  return base||cleaned;
}
""".replace("{marker}", MARKER)


def write_module(root: Path) -> str:
    path = root / "sidecars" / "panel" / MODULE
    if path.is_file() and path.read_text(encoding="utf-8") == HELPER_MODULE:
        return "module up to date"
    path.write_text(HELPER_MODULE, encoding="utf-8")
    return "module written"


def patch_usage(root: Path) -> str:
    path = root / "sidecars" / "panel" / "usage.mjs"
    src = path.read_text(encoding="utf-8")
    if MARKER in src:
        return "already patched"
    imp = "import {discoverLocalConversations,conversationId} from './local-conversations.mjs';"
    if imp not in src:
        print("  ! anchor import not found in usage.mjs")
        return "FAILED"
    src = src.replace(
        imp,
        imp + "\n// " + MARKER + ": merge statistics series by model family\n"
            "import {mergedModelName} from './" + MODULE + "';",
        1,
    )
    old = "model:cleanModel(chat.modelDisplayName||chat.responseModel||u.model||chat.model),"
    if old not in src:
        print("  ! row source not found in usage.mjs")
        return "FAILED"
    src = src.replace(old, "model:mergedModelName(chat.modelDisplayName||chat.responseModel||u.model||chat.model),", 1)
    path.write_text(src, encoding="utf-8")
    return "patched"


def patch_worker(root: Path) -> str:
    path = root / "sidecars" / "panel" / "usage-disk-worker.mjs"
    src = path.read_text(encoding="utf-8")
    if MARKER in src:
        return "already patched"
    imp = "import {TrajectoryJson} from './trajectory-json.mjs';"
    if imp not in src:
        print("  ! anchor import not found in usage-disk-worker.mjs")
        return "FAILED"
    src = src.replace(
        imp,
        imp + "\n// " + MARKER + ": normalise legacy rows to the merged family name too\n"
            "import {mergedModelName} from './" + MODULE + "';",
        1,
    )
    src = re.sub(r"model\.run\(r\.model\)", "model.run(mergedModelName(r.model))", src)
    src = re.sub(r"bucket\.run\(recordDate\(r\.at\),r\.model,", "bucket.run(recordDate(r.at),mergedModelName(r.model),", src)
    path.write_text(src, encoding="utf-8")
    return "patched"


def patch_budget(root: Path) -> str:
    """Raise the retained-payload budget so long conversations can complete."""
    targets = {
        "sidecars/panel/trajectory-json.mjs": [("maxRetainedBytes=8*1024*1024", "maxRetainedBytes=" + str(BUDGET))],
        "sidecars/panel/trajectory-reader.mjs": [("budgetBytes=8*1024*1024", "budgetBytes=" + str(BUDGET))],
        "sidecars/panel/delegated-usage.mjs": [("budgetBytes=8*1024*1024", "budgetBytes=" + str(BUDGET))],
        "sidecars/panel/client.mjs": [("maxRetainedBytes:8*1024*1024", "maxRetainedBytes:" + str(BUDGET))],
        # a single trajectory record may exceed 8 MiB on long conversations
        "sidecars/panel/disk-statistics.mjs": [("Buffer.byteLength(j)>8*1024*1024", "Buffer.byteLength(j)>" + str(BUDGET))],
        "sidecars/panel/usage.mjs": [("BACKFILL_BYTES=8*1024*1024", "BACKFILL_BYTES=" + str(BUDGET))],
        # the background collection worker needs heap for the larger payload
        "sidecars/panel/background-statistics.mjs": [("maxOldGenerationSizeMb:96", "maxOldGenerationSizeMb:768"), ("maxOldGenerationSizeMb:256", "maxOldGenerationSizeMb:768")],
        "sidecars/panel/usage.mjs": [("maxOldGenerationSizeMb:64", "maxOldGenerationSizeMb:768"), ("maxOldGenerationSizeMb:256", "maxOldGenerationSizeMb:768")],
    }
    touched = []
    for rel, subs in targets.items():
        path = root / rel
        if not path.is_file():
            continue
        src = path.read_text(encoding="utf-8")
        orig = src
        for old, new in subs:
            src = src.replace(old, new)
        if src != orig:
            path.write_text(src, encoding="utf-8")
            touched.append(rel.split("/")[-1])
    return ("raised: " + ", ".join(touched)) if touched else "already raised / no match"


def patch_staging_path(root: Path) -> str:
    """Keep the SQLite staging file name short.

    Upstream builds the staging path as `<ledger.json>.<uuid>.tmp`. The usage
    ledger path is already ~218 characters on a normal profile, and SQLite
    creates a "-journal" sidecar (8 more characters) next to it. That pushed
    the path past the Windows MAX_PATH limit, and the disk worker died with
    "unable to open database file" - the collection then ended in state
    "limited" / code "budget-exceeded". Same directory, short name.
    """
    path = root / "sidecars" / "panel" / "usage.mjs"
    if not path.is_file():
        return "usage.mjs not found"
    src = path.read_text(encoding="utf-8")
    if "PULSE_STAGING_PATH_V1" in src:
        return "already patched"
    old = "const staging=file+'.'+randomUUID()+'.tmp';"
    if old not in src:
        return "anchor not found"
    new = ("// PULSE_STAGING_PATH_V1: keep the staging name short - SQLite adds a\n"
           "      // \"-journal\" sidecar (8 more chars) and the ledger path is already ~218\n"
           "      // chars here, which pushed it past the Windows MAX_PATH limit.\n"
           "      const staging=join(dirname(file),'s'+randomUUID().replace(/-/g,'')+'.tmp');")
    src = src.replace(old, new, 1)
    if "import {join} from 'node:path';" in src:
        src = src.replace("import {join} from 'node:path';", "import {join,dirname} from 'node:path';", 1)
    path.write_text(src, encoding="utf-8")
    return "patched"


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".gemini" / "config" / "plugins" / "antigravity-pulse"
    usage = root / "sidecars" / "panel" / "usage.mjs"
    if not usage.is_file():
        print("not found: " + str(usage))
        return 1
    print(MODULE + ": " + write_module(root))
    print("usage.mjs: " + patch_usage(root))
    print("usage-disk-worker.mjs: " + patch_worker(root))
    print("budget: " + patch_budget(root))
    print("staging path: " + patch_staging_path(root))
    text = usage.read_text(encoding="utf-8")
    worker = (root / "sidecars" / "panel" / "usage-disk-worker.mjs").read_text(encoding="utf-8")
    helper = (root / "sidecars" / "panel" / MODULE).read_text(encoding="utf-8")
    tj = (root / "sidecars" / "panel" / "trajectory-json.mjs").read_text(encoding="utf-8")
    ok = ("model:mergedModelName(" in text
          and "mergedModelName(r.model)" in worker
          and "FAMILIES" in helper
          and "maxRetainedBytes=" + str(BUDGET) in tj)
    print("verify: " + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
