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
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


def norm(name):
    """Dedupe key: casefold + straight apostrophes + collapsed whitespace."""
    s = unicodedata.normalize("NFKC", name).replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", s).strip().casefold()


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
    try:  # curated catalog imported from a shared dump; may not exist in older db copies
        boon_lib = rows(cur, "select name, rarity, description, quote from boon_lib")
    except sqlite3.OperationalError:
        boon_lib = []
    affix_lib = rows(cur, "select name, description, first_ripple from affix_lib")
    affix_run = rows(cur, "select name, ripple from affix_run")
    bosses = [r["boss"] for r in rows(cur, "select distinct boss from waves where boss != ''")]

    for r in offers + claims:
        r["run"] = int(r["run"] or 0)
        r["ripple"] = int(r["ripple"] or 0)
    for r in claims:
        r["echoes"] = int(r["echoes"] or 0)

    # ---- boon catalog: curated boon_lib first, overlaid with in-game observations.
    # Deduped by normalized name; the lib's rarity/description/quote win (full, untruncated),
    # observations contribute lastSeen and any boons the lib doesn't know about.
    boons = {}
    for r in boon_lib:
        boons[norm(r["name"])] = {"name": r["name"], "rarity": r["rarity"] or "",
                                  "description": r["description"] or "",
                                  "quote": r["quote"] or "", "lastSeen": ""}
    def observed(name):
        return boons.setdefault(norm(name), {"name": name, "rarity": "", "description": "",
                                             "quote": "", "lastSeen": ""})
    for r in offers:
        b = observed(r["name"])
        if r["description"] and not b["description"]:
            b["description"] = r["description"]
        b["lastSeen"] = max(b["lastSeen"], r["ts"] or "")
    for r in claims:
        b = observed(r["name"])
        if r["rarity"] and not b["rarity"]:
            b["rarity"] = r["rarity"].lower()
        if r["description"] and not b["description"]:
            b["description"] = r["description"]
        b["lastSeen"] = max(b["lastSeen"], r["ts"] or "")
    boon_list = []
    for b in sorted(boons.values(), key=lambda b: b["name"].lower()):
        boon_list.append({
            "name": b["name"], "rarity": b["rarity"], "description": b["description"],
            "quote": b["quote"], "lastSeen": b["lastSeen"][:10],
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
        "totals": {"boons": len(boon_list), "affixes": len(affix_list),
                   "bosses": len(boss_list)},
    }

    out = here / "data.js"
    out.write_text("window.BOON_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n")
    print(f"wrote {out} ({len(boon_list)} boons, {len(affix_list)} affixes, "
          f"{len(boss_list)} bosses)")


if __name__ == "__main__":
    main()
