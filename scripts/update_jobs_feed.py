#!/usr/bin/env python3
import hashlib, json, re, time, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape

FEEDS = [
    ("FL.ru", "https://www.fl.ru/rss/all.xml?category=5"),
    ("Freelancehunt", "https://freelancehunt.com/projects.rss"),
]
GOOD = re.compile(r"\b(сайт|сайта|сайтов|лендинг|landing|верстк|html|css|javascript|frontend|front-end|веб|web|wordpress|tilda|тильда|интернет-магазин|telegram mini app|мини.?апп|бот|автоматизац|интеграц|no.?code|figma)\b", re.I)
BEGINNER = re.compile(r"\b(прост(ой|ая|ое)|небольш(ой|ая|ое)|лендинг|сайт-визитк|tilda|тильда|wordpress|правк|доработк|адаптив|верстк|html|css)\b", re.I)
EXCLUDE = re.compile(r"\b(1с|1c|крипто|трейдинг|парсинг|взлом|ферм[аы]|обход|казино|ставк|видеомонтаж|логотип|дизайн карточек|seo)\b", re.I)

def clean(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", unescape(value)).strip()

def parse_date(value):
    if not value: return ""
    try: return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except Exception: return value

def fetch(source, url):
    req = urllib.request.Request(url, headers={"User-Agent":"FinanceHQ-JobFeed/1.0"})
    with urllib.request.urlopen(req, timeout=25) as response:
        root = ET.fromstring(response.read())
    rows=[]
    for item in root.findall(".//item"):
        title=clean(item.findtext("title"))
        link=clean(item.findtext("link"))
        desc=clean(item.findtext("description"))
        haystack=title+" "+desc
        if not title or not link or not GOOD.search(haystack) or EXCLUDE.search(title):
            continue
        pub=parse_date(item.findtext("pubDate"))
        budget_match=re.search(r"(?:бюджет\s*[:—-]?\s*)?(\d[\d\s.,]{1,12})\s*(₽|руб\.?|UAH|грн)", haystack, re.I)
        budget=0
        if budget_match:
            try: budget=int(float(re.sub(r"\s","",budget_match.group(1)).replace(",", ".")))
            except Exception: budget=0
        rows.append({
            "id": source.lower()+"-"+hashlib.sha1(link.encode("utf-8")).hexdigest()[:14],
            "title": title[:220], "url": link, "source": source,
            "publishedAt": pub, "summary": desc[:420],
            "budget": budget,
            "beginnerFriendly": bool(BEGINNER.search(haystack))
        })
    return rows

jobs=[]
errors=[]
for source,url in FEEDS:
    try: jobs.extend(fetch(source,url))
    except Exception as exc: errors.append(source+": "+str(exc)[:180])

# Newest first; stable de-duplication by URL.
seen=set(); unique=[]
for job in jobs:
    if job["url"] in seen: continue
    seen.add(job["url"]); unique.append(job)
unique.sort(key=lambda x:x["publishedAt"], reverse=True)
payload={
    "updatedAt": datetime.now(timezone.utc).isoformat(),
    "sources": [s for s,_ in FEEDS],
    "errors": errors,
    "jobs": unique[:60]
}
with open("jobs-feed.json","w",encoding="utf-8") as f:
    json.dump(payload,f,ensure_ascii=False,indent=2)
print("Saved",len(payload["jobs"]),"matching jobs; source errors:",len(errors))
