import os

from dotenv import load_dotenv
from pytrends.request import TrendReq


load_dotenv()

keyword = os.getenv("TRENDS_TEST_KEYWORD", "iPhone")
timeframe = os.getenv("TRENDS_TEST_TIMEFRAME", "now 7-d")
proxy_values = [
    value.strip()
    for value in os.getenv("GOOGLE_TRENDS_PROXIES", "").split(",")
    if value.strip()
]

trends_options = {
    "hl": "en-US",
    "tz": 300,
    "geo": "",
    "retries": 0,
    "backoff_factor": 0,
    "timeout": (10, 30),
}
if proxy_values:
    trends_options["proxies"] = proxy_values


def main():
    pytrends = TrendReq(**trends_options)
    pytrends.build_payload([keyword], timeframe=timeframe)

    interest = pytrends.interest_over_time()
    related = pytrends.related_queries() or {}
    query_data = related.get(keyword) or next(iter(related.values()), {})
    top = query_data.get("top")
    rising = query_data.get("rising")

    print(f"keyword={keyword!r} timeframe={timeframe!r} geo=worldwide")
    print(f"interest_points={len(interest) if interest is not None else 0}")
    print(f"top_queries={len(top) if top is not None else 0}")
    print(f"rising_queries={len(rising) if rising is not None else 0}")
    if interest is not None and not interest.empty:
        print(interest[[keyword]].tail(5).to_string())
    if rising is not None and not rising.empty:
        print(rising.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
