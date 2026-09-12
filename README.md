# Mnemosyne Boon Database

Static site publishing the Tides of Memory boon data sourced from Laorir's
Mnemosyne API (Achaea).

Live: https://mediaresachaea.github.io/mnemosyne-boons/

## Updating

```sh
./publish.sh
```

That re-exports `data.js` from the Mudlet profile's `Database_mnemosyne.db`
(the `config` table — API token etc. — is never exported), commits, and pushes.
GitHub Pages redeploys automatically on push.

To export without publishing: `python3 export_site.py [path/to/Database_mnemosyne.db]`.

## Automatic updates

`.github/workflows/update-boons.yml` runs daily (09:17 UTC, or on demand from the
Actions tab). It runs `update_from_api.py`, which merges the live export from
`http://104.128.56.238:8000/boons/export` into `data.js`, and pushes if anything changed.
The API's rarity, description, quote and echo text win; boons the API doesn't have, plus
affixes and bosses, are kept as they are.

To run it by hand: `python3 update_from_api.py`. Note that `./publish.sh` rebuilds
`data.js` from the Mudlet db alone, so API-only boons drop off the site until the next
daily run (or run `update_from_api.py` before pushing).
