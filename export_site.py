#!/usr/bin/env python3
"""Export Database_mnemosyne.db (Mudlet SQLite) to data.js for the static boon site.

Reads the offers/claims/affix_lib/affix_run/waves tables and emits an aggregated
window.BOON_DATA payload. The `config` table (API token etc.) is never read.

Usage: python3 export_site.py [path/to/Database_mnemosyne.db]
Default db path: ../../Database_mnemosyne.db relative to this script
(i.e. the TreyalLegacy profile root when this repo lives in Homebrew/).
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

RARITY_ORDER = {"legendary": 0, "rare": 1, "uncommon": 2, "common": 3, "": 4}


def rows(cur, sql, args=()):
    cur.execute(sql, args)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def main():
    here = Path(__file__).resolve().parent
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else here.parents[1] / "Database_mnemosyne.db"
    if not db_path.exists():
        sys.exit(f"db not found: {db_path}")

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = con.cursor()

    offers = rows(cur, "select run, ripple, name, description, ts from offers")
    claims = rows(cur, "select run, ripple, name, echoes, rarity, description, ts from claims")
    affix_lib = rows(cur, "select name, description, first_run, first_ripple from affix_lib")
    affix_run = rows(cur, "select run, ripple, name, description from affix_run")
    waves = rows(cur, "select run, ripple, monsters, boss from waves")

    for r in offers + claims + affix_run + waves:
        r["run"] = int(r["run"] or 0)
        r["ripple"] = int(r["ripple"] or 0)
    for r in claims:
        r["echoes"] = int(r["echoes"] or 0)
    for r in affix_lib:
        r["first_run"] = int(r["first_run"] or 0)
        r["first_ripple"] = int(r["first_ripple"] or 0)

    # ---- boon catalog: one entry per distinct name across offers + claims
    boons = {}
    for r in offers:
        b = boons.setdefault(r["name"], {"name": r["name"], "rarity": "", "description": "",
                                         "offeredKeys": set(), "claims": 0, "claimRuns": set(),
                                         "maxEchoes": 0, "lastSeen": ""})
        b["offeredKeys"].add((r["run"], r["ripple"]))
        if r["description"]:
            b["description"] = r["description"]  # latest wins (rows are insert-ordered)
        b["lastSeen"] = max(b["lastSeen"], r["ts"] or "")
    for r in claims:
        b = boons.setdefault(r["name"], {"name": r["name"], "rarity": "", "description": "",
                                         "offeredKeys": set(), "claims": 0, "claimRuns": set(),
                                         "maxEchoes": 0, "lastSeen": ""})
        b["claims"] += 1
        b["claimRuns"].add(r["run"])
        b["maxEchoes"] = max(b["maxEchoes"], r["echoes"])
        if r["rarity"]:
            b["rarity"] = r["rarity"].lower()
        if r["description"] and not b["description"]:
            b["description"] = r["description"]
        b["lastSeen"] = max(b["lastSeen"], r["ts"] or "")
    boon_list = []
    for b in sorted(boons.values(), key=lambda b: b["name"].lower()):
        boon_list.append({
            "name": b["name"], "rarity": b["rarity"], "description": b["description"],
            "offered": len(b["offeredKeys"]), "claims": b["claims"],
            "claimRuns": len(b["claimRuns"]), "maxEchoes": b["maxEchoes"],
            "lastSeen": b["lastSeen"][:10],
        })

    # ---- runs: claims + affixes + bosses grouped per run
    runs = {}
    def run_of(n):
        return runs.setdefault(n, {"run": n, "maxRipple": 0, "started": "", "ended": "",
                                   "claims": [], "affixes": [], "bosses": []})
    for r in claims:
        run = run_of(r["run"])
        run["maxRipple"] = max(run["maxRipple"], r["ripple"])
        run["claims"].append({"ripple": r["ripple"], "name": r["name"],
                              "rarity": (r["rarity"] or "").lower(), "echoes": r["echoes"]})
        ts = r["ts"] or ""
        run["started"] = min(filter(None, [run["started"], ts]), default=ts)
        run["ended"] = max(run["ended"], ts)
    for r in offers:
        run = run_of(r["run"])
        run["maxRipple"] = max(run["maxRipple"], r["ripple"])
        ts = r["ts"] or ""
        run["started"] = min(filter(None, [run["started"], ts]), default=ts)
        run["ended"] = max(run["ended"], ts)
    for r in affix_run:
        run = run_of(r["run"])
        if r["name"] not in [a["name"] for a in run["affixes"]]:
            run["affixes"].append({"name": r["name"], "ripple": r["ripple"]})
    for r in waves:
        run = run_of(r["run"])
        run["maxRipple"] = max(run["maxRipple"], r["ripple"])
        if r["boss"] and r["boss"] not in [b["name"] for b in run["bosses"]]:
            run["bosses"].append({"name": r["boss"], "ripple": r["ripple"]})
    run_list = []
    for run in sorted(runs.values(), key=lambda r: -r["run"]):
        run["claims"].sort(key=lambda c: (c["ripple"], c["name"]))
        run["date"] = run["started"][:10]
        del run["started"], run["ended"]
        run_list.append(run)

    # ---- bosses: distinct, with sighting counts
    bosses = {}
    for r in waves:
        if not r["boss"]:
            continue
        b = bosses.setdefault(r["boss"], {"name": r["boss"], "seen": 0, "runs": set(), "ripples": set()})
        b["seen"] += 1
        b["runs"].add(r["run"])
        b["ripples"].add(r["ripple"])
    boss_list = [{"name": b["name"], "seen": b["seen"], "runs": len(b["runs"]),
                  "ripples": sorted(b["ripples"])}
                 for b in sorted(bosses.values(), key=lambda b: b["name"].lower())]

    affix_list = [{"name": a["name"], "description": a["description"],
                   "firstRun": a["first_run"], "firstRipple": a["first_ripple"]}
                  for a in sorted(affix_lib, key=lambda a: a["name"].lower())]

    data = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "boons": boon_list, "runs": run_list, "affixes": affix_list, "bosses": boss_list,
        "totals": {"boons": len(boon_list), "runs": len(run_list),
                   "claims": len(claims), "affixes": len(affix_list),
                   "deepest": max((r["maxRipple"] for r in run_list), default=0)},
    }

    out = here / "data.js"
    out.write_text("window.BOON_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n")
    print(f"wrote {out} ({len(boon_list)} boons, {len(run_list)} runs, "
          f"{len(affix_list)} affixes, {len(boss_list)} bosses)")


if __name__ == "__main__":
    main()
