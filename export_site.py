#!/usr/bin/env python3
"""Export Database_mnemosyne.db (Mudlet SQLite) to data.js for the static boon site.

Publishes the boon catalog, the affix library (name/description/earliest ripple), and
the boss name list. Per-run history and sighting details stay private, and the
`config` table (API token etc.) is never read.

Usage: python3 export_site.py [path/to/Database_mnemosyne.db]
Default db path: ../../Database_mnemosyne.db relative to this script
(i.e. the TreyalLegacy profile root when this repo lives in Homebrew/).
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


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
    affix_lib = rows(cur, "select name, description, first_ripple from affix_lib")
    affix_run = rows(cur, "select name, ripple from affix_run")
    bosses = [r["boss"] for r in rows(cur, "select distinct boss from waves where boss != ''")]

    for r in offers + claims:
        r["run"] = int(r["run"] or 0)
        r["ripple"] = int(r["ripple"] or 0)
    for r in claims:
        r["echoes"] = int(r["echoes"] or 0)

    # ---- boon catalog: one entry per distinct name across offers + claims
    boons = {}
    for r in offers:
        b = boons.setdefault(r["name"], {"name": r["name"], "rarity": "", "description": "",
                                         "offeredKeys": set(), "claims": 0,
                                         "maxEchoes": 0, "lastSeen": ""})
        b["offeredKeys"].add((r["run"], r["ripple"]))
        if r["description"]:
            b["description"] = r["description"]  # latest wins (rows are insert-ordered)
        b["lastSeen"] = max(b["lastSeen"], r["ts"] or "")
    for r in claims:
        b = boons.setdefault(r["name"], {"name": r["name"], "rarity": "", "description": "",
                                         "offeredKeys": set(), "claims": 0,
                                         "maxEchoes": 0, "lastSeen": ""})
        b["claims"] += 1
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
            "maxEchoes": b["maxEchoes"], "lastSeen": b["lastSeen"][:10],
        })

    # ---- affixes: name + description + earliest ripple ever seen (no run numbers)
    earliest = {}
    for r in affix_run:
        rip = int(r["ripple"] or 0)
        if rip > 0:
            earliest[r["name"]] = min(earliest.get(r["name"], rip), rip)
    affix_list = []
    for a in sorted(affix_lib, key=lambda a: a["name"].lower()):
        first = int(a["first_ripple"] or 0)
        rip = earliest.get(a["name"], first)
        if first > 0:
            rip = min(rip or first, first)
        affix_list.append({"name": a["name"], "description": a["description"],
                           "earliestRipple": rip})

    boss_list = sorted(bosses, key=str.lower)

    data = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "boons": boon_list, "affixes": affix_list, "bosses": boss_list,
        "totals": {"boons": len(boon_list), "claims": len(claims),
                   "affixes": len(affix_list), "bosses": len(boss_list)},
    }

    out = here / "data.js"
    out.write_text("window.BOON_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n")
    print(f"wrote {out} ({len(boon_list)} boons, {len(affix_list)} affixes, "
          f"{len(boss_list)} bosses)")


if __name__ == "__main__":
    main()
