"""Inspect a real HEnEx DAM Results Summary XLSX to learn its layout."""
from datetime import date
from io import BytesIO
from openpyxl import load_workbook
from optimisation.henex_dam import fetch_dam_xlsx

raw, url = fetch_dam_xlsx(date(2026, 4, 29))
print("URL:", url)
print("SIZE:", len(raw))

# Save it for offline inspection
out = "/tmp/enex_sample.xlsx"
with open(out, "wb") as f:
    f.write(raw)
print("Saved:", out)

wb = load_workbook(BytesIO(raw), data_only=True)
print("SHEETS:", wb.sheetnames)

for sheet_name in wb.sheetnames:
    ws = wb[sheet_name]
    print(f"\n=== {sheet_name}  rows={ws.max_row}  cols={ws.max_column} ===")
    for i, r in enumerate(ws.iter_rows(values_only=True, max_row=50)):
        cells = [(str(c)[:25] if c is not None else "") for c in r[:14]]
        print(f"  {i:>3}: {cells}")
