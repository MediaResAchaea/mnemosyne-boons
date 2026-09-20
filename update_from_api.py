#!/usr/bin/env python3
"""Merge the live boon export from the Mnemosyne API into data.js.

The API is the source of truth for boon text: its rarity, description, quote and echo
text override what data.js has. Boons the API doesn't know about, plus the affixes and
bosses (which it doesn't export), are kept as they are. `generated` is only bumped when
the boon data actually changes, so a no-op run leaves data.js untouched.

Usage: python3 update_from_api.py [export-url]
Default url: http://104.128.56.238:8000/boons/export
"""

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from export_site import norm

EXPORT_URL = "http://104.128.56.238:8000/boons/export"
PREFIX = "window.BOON_DATA = "


def squash(s):
    return re.sub(r"\s+", " ", s or "").strip()


def clean(text, names, conflicts):
    """Strip in-game info-panel fragments the tracker sometimes glues onto boon text:
    a 'Category: X' or 'Conflicts With: Y' label, or the wrapped tail of an
    'Unlocked By' boon name (e.g. 'of Sycaerunax Your draconic blast...')."""
    s = re.sub(r"^Category: \w+ ", "", squash(text))
    if conflicts and s.startswith("Conflicts With: "):
        label = "Conflicts With: " + ", ".join(conflicts) + " "
        if s.startswith(label):
            s = s[len(label):]
    if s[:1].islower():
        for name in names:
            words = name.split()
            for i in range(1, len(words)):
                frag = " ".join(words[i:]) + " "
                if s.startswith(frag) and s[len(frag):][:1].isupper():
                    return s[len(frag):]
    return s


def fetch(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        export = json.load(r)
    if not isinstance(export, list) or not export:
        sys.exit(f"export from {url} is not a non-empty list")
    # A boon only needs a name: the tracker sometimes records one before anyone has seen its
    # text (description/echoes null), and merge() keeps whatever data.js already has for the
    # missing fields. Records without a name are skipped rather than failing the whole run.
    good = []
    for b in export:
        if not (isinstance(b, dict) and isinstance(b.get("name"), str) and b["name"].strip()):
            print(f"skipping malformed boon in export: {str(b)[:200]}", file=sys.stderr)
            continue
        for key in ("description", "quote", "rarity", "updated_at"):
            if not isinstance(b.get(key), str):
                b[key] = None
        if not isinstance(b.get("echoes"), list):
            b["echoes"] = None
        good.append(b)
    if not good:
        sys.exit(f"export from {url} has no usable boons")
    return good


def merge(site_boons, export):
    names = [b["name"] for b in export]
    boons = {norm(b["name"]): dict(b) for b in site_boons}
    for e in export:
        b = boons.setdefault(norm(e["name"]), {"name": "", "rarity": "", "description": "",
                                               "quote": "", "echoDescription": "",
                                               "lastSeen": ""})
        conflicts = e.get("conflicts_with")
        b["name"] = squash(e["name"])
        b["rarity"] = (e.get("rarity") or "").lower() or b["rarity"]
        b["description"] = clean(e["description"], names, conflicts) or b["description"]
        b["quote"] = squash(e.get("quote")) or b["quote"]
        echoes = sorted((x for x in e.get("echoes") or []
                         if isinstance(x, dict) and isinstance(x.get("description"), str)),
                        key=lambda x: x.get("echo_number") or 0)
        if echoes:  # the site shows one "Echoed:" line: the highest echo the API has text for
            b["echoDescription"] = clean(echoes[-1]["description"], names, conflicts)
        b["lastSeen"] = max(b["lastSeen"], (e.get("updated_at") or "")[:10])
    return sorted(boons.values(), key=lambda b: b["name"].lower())


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else EXPORT_URL
    out = Path(__file__).resolve().parent / "data.js"
    text = out.read_text(encoding="utf-8")
    if not text.startswith(PREFIX):
        sys.exit(f"{out} doesn't start with {PREFIX!r}")
    data = json.loads(text[len(PREFIX):].rstrip().rstrip(";"))

    export = fetch(url)
    old = {norm(b["name"]): b for b in data["boons"]}
    boons = merge(data["boons"], export)
    added = sum(1 for b in boons if norm(b["name"]) not in old)
    changed = sum(1 for b in boons if norm(b["name"]) in old and old[norm(b["name"])] != b)
    if not added and not changed:
        print(f"no boon changes ({len(export)} boons in export)")
        return

    data["boons"] = boons
    data["totals"]["boons"] = len(boons)
    data["generated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out.write_text(PREFIX + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"wrote {out} ({len(export)} boons in export, {len(boons)} total: "
          f"{added} new, {changed} updated)")


if __name__ == "__main__":
    main()
