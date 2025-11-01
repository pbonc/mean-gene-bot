import logging
from typing import List, Dict
import gspread
from google.oauth2.service_account import Credentials

LOG = logging.getLogger("google_sheets_sync")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _build_client(json_key_path: str):
    creds = Credentials.from_service_account_file(json_key_path, scopes=SCOPES)
    return gspread.authorize(creds)


def write_full_sheet(json_key_path: str, spreadsheet_id: str, sheet_name: str, rows: List[Dict]):
    """Overwrite the target sheet with the provided rows.

    rows: list of dicts; keys used as header columns (order from first dict).
    """
    client = _build_client(json_key_path)
    sh = client.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=max(100, len(rows) + 10), cols=10)

    if not rows:
        # clear sheet but keep header empty
        ws.clear()
        LOG.info("Wrote 0 rows to sheet %s/%s", spreadsheet_id, sheet_name)
        return

    headers = list(rows[0].keys())
    values = [headers]
    for r in rows:
        values.append([r.get(h, "") for h in headers])

    ws.clear()
    ws.update(values)
    LOG.info("Wrote %d rows to sheet %s/%s", len(rows), spreadsheet_id, sheet_name)
