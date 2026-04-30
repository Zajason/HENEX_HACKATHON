"""Probe HEnEx page for actual XLSX download URLs."""
import re
from urllib.request import Request, urlopen

UA = "Mozilla/5.0"
PAGE = "https://www.enexgroup.gr/markets-publications-el-day-ahead-market"

req = Request(PAGE, headers={"User-Agent": UA})
with urlopen(req, timeout=30) as r:
    html = r.read().decode("utf-8", errors="replace")

print(f"Page bytes: {len(html)}")

xlsx = sorted(set(re.findall(r'(https?://[^"\'<>]+\.xlsx[^"\'<>]*)', html)))
print(f"XLSX links found: {len(xlsx)}")
for u in xlsx[:25]:
    print(" -", u)

dam = [u for u in xlsx if "DAM" in u or "dam" in u]
print(f"DAM-related: {len(dam)}")
for u in dam[:25]:
    print(" *", u)
