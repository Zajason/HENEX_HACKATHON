"""Debug what the parser sees on the real XLSX."""
from io import BytesIO
from openpyxl import load_workbook

with open("/tmp/enex_sample.xlsx", "rb") as f:
    raw = f.read()

wb = load_workbook(filename=BytesIO(raw), data_only=True)
print("All sheet names:", wb.sheetnames)
for name in wb.sheetnames:
    ws = wb[name]
    has_iter = hasattr(ws, "iter_rows")
    print(f"  {name!r}: type={type(ws).__name__} iter_rows={has_iter}")
    if not has_iter:
        continue
    # show first column label of every row
    for i, row in enumerate(ws.iter_rows(values_only=True, max_row=12)):
        if not row:
            continue
        lbl = row[0]
        print(f"    row {i}: label={lbl!r} (numeric_count={sum(1 for c in row[1:97] if isinstance(c, (int, float)))})")
