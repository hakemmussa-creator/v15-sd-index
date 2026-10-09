# Updating the index page

1. Download the current Excel index (`SD Index V15 - Drive Links RevXX.xlsx`) from the drawings folder in Google Drive.
2. Run:

   ```
   pip install openpyxl cryptography
   V15_PASSWORD='<team password>' python3 tools/build_page.py "SD Index V15 - Drive Links RevXX.xlsx" --old index.html --report report.json
   ```

   - `--old index.html` decrypts the live page and lists what changed.
   - `missing_links` lists refs typed in the sheet that have no Drive folder link yet. Find each folder in Drive (folders are named by ref) and pass them with `--links extra.json` ({"ARC-099": "https://drive.google.com/drive/folders/<id>"}).
3. Commit the new `index.html` and push to `main`. GitHub Pages republishes in about a minute.

The password and the Drive links are never stored in this repository in readable form; the data is AES-256 encrypted inside `index.html`.

## MAS / PQN private index (`submittals.html`)

Built by `build_submittals.py` + `submittals_template.html` from the Unifier CSV exports (Reference No, Revision No., Title, Discipline).
Its password is separate from the shop drawing index and is passed only as the env var `SUB_PASSWORD`.
Add Drive folder links later without the CSVs:

    SUB_PASSWORD='...' python3 tools/build_submittals.py --old submittals.html --links links.json --out submittals.html

## Updates panel (both pages)

Each page has an encrypted "Updates" list (one collapsible day per update run), stored in `const UPD` and
encrypted with that page's own password. Rebuilds with `--old <page>` carry it forward. Add a day with:

    PAGE_PASSWORD='...' python3 tools/add_updates.py index.html day.json

## Status colours (v2 layout)

Both pages colour each reference by its latest Unifier status (green A/B, red C/D/F, yellow under review, grey E),
stored encrypted in `const STA` and carried forward by rebuilds with `--old`. Refresh it with:

    PAGE_PASSWORD='...' python3 tools/set_status.py index.html status.json   # {"SD-ARC-052": ["B", 2], ...}

Sections are collapsible (+/−), with status filter chips; the Updates panel is one collapsible table sorted by date.
