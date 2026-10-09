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
