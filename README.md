# Mnemosyne Boon Database

Static site publishing the Tides of Memory boon data captured in-game by the
`mnemosyne.lua` Mudlet tracker (Achaea, Treyal).

Live: https://mediaresachaea.github.io/mnemosyne-boons/

## Updating

```sh
./publish.sh
```

That re-exports `data.js` from the Mudlet profile's `Database_mnemosyne.db`
(the `config` table — API token etc. — is never exported), commits, and pushes.
GitHub Pages redeploys automatically on push.

To export without publishing: `python3 export_site.py [path/to/Database_mnemosyne.db]`.
