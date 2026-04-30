"""Extract real DAM XLSX URLs from the HEnEx Day-Ahead Market page."""
import re
from urllib.request import Request, urlopen

UA = "Mozilla/5.0"
PAGE = "https://www.enexgroup.gr/markets-publications-el-day-ahead-market"

req = Request(PAGE, headers={"User-Agent": UA})
with urlopen(req, timeout=30) as r:
    html = r.read().decode("utf-8", errors="replace")

# Find each <a ...>FILENAME</a> for DAM files: capture href + filename
pattern = re.compile(
    r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>'
    r'\s*(?:<[^>]+>\s*)*'
    r'(\d{8}_EL-DAM_ResultsSummary_[A-Z]{2}_v\d{2}\.xlsx)\s*</a>',
    re.IGNORECASE,
)
matches = pattern.findall(html)
print(f"Matches: {len(matches)}")
for href, fname in matches[:20]:
    print(f"  {fname}\n    -> {href}")

# Also dump 200-char window around each filename mention to confirm URL pattern
for m in re.finditer(r'(\d{8}_EL-DAM_ResultsSummary_EN_v\d{2}\.xlsx)', html):
    s = max(0, m.start() - 250)
    e = min(len(html), m.end() + 50)
    print(f"\n--- around {m.group(1)} ---")
    print(html[s:e])
