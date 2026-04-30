"""Probe HEnEx alternative archive pages for older DAM XLSX files."""
import re
from urllib.request import Request, urlopen

UA = "Mozilla/5.0"

def fetch(url):
    try:
        with urlopen(Request(url, headers={"User-Agent": UA}), timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"ERR: {e}"

def count_dam(html):
    if html.startswith("ERR"):
        return html, []
    found = re.findall(r'(\d{8})_EL-DAM_ResultsSummary_EN_v(\d{2})\.xlsx', html)
    days = sorted(set(m[0] for m in found), reverse=True)
    return f"{len(html)} bytes, {len(days)} unique days", days

candidates = [
    "https://www.enexgroup.gr/markets-reports",
    "https://www.enexgroup.gr/dam-idm-archive",
    "https://www.enexgroup.gr/web/guest/markets-publications-el-day-ahead-market",
    # try with _resetCur=true and explicit cur
    "https://www.enexgroup.gr/markets-publications-el-day-ahead-market?p_p_id=com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_5OlL6oMjSb0W&p_p_lifecycle=0&p_p_state=normal&_com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_5OlL6oMjSb0W_cur=2",
    "https://www.enexgroup.gr/markets-publications-el-day-ahead-market?p_p_id=com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_5OlL6oMjSb0W&p_p_state=normal&_com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_5OlL6oMjSb0W_cur=2&_com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_5OlL6oMjSb0W_resetCur=false",
]

for url in candidates:
    info, days = count_dam(fetch(url))
    print(f"{url}\n  {info}")
    if days:
        print(f"  range: {days[-1]} -> {days[0]}")

# Try Liferay search portlet with keyword
search_url = "https://www.enexgroup.gr/search?_com_liferay_portal_search_web_portlet_SearchPortlet_keywords=DAM_ResultsSummary"
print(f"\nSearch endpoint:")
info, days = count_dam(fetch(search_url))
print(f"  {info}")
if days:
    print(f"  range: {days[-1]} -> {days[0]}")
