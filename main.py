from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import httpx
import re
import os
import pathlib

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "d3fd1e720fmsh6ff53a31e928ecdp19fa06jsn4d98e98c079c")

class SearchRequest(BaseModel):
    niche: str
    city: str = ""
    platform: str = "google"
    maxItems: int = 10

def extract_email(text):
    m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-z]{2,}', text or "")
    return m.group(0) if m else ""

def extract_phone(text):
    m = re.search(r'[\+]?[\d][\d\s\-().]{7,}', text or "")
    return m.group(0).strip() if m else ""

async def search_google(niche, city, max_items):
    query = f"{niche} {city} contact email".strip()
    url = "https://google-search74.p.rapidapi.com/"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "google-search74.p.rapidapi.com"
    }
    params = {"query": query, "limit": max_items, "related_keywords": "true"}
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(url, headers=headers, params=params)
        data = res.json()
    results = data.get("results", [])
    leads = []
    for i, item in enumerate(results[:max_items]):
        desc = (item.get("description") or "") + " " + (item.get("url") or "")
        url_val = item.get("url") or ""
        leads.append({
            "id": i+1,
            "name": item.get("title") or "Unknown",
            "handle": "—",
            "instaLink": url_val if "instagram.com" in url_val else None,
            "linkedinLink": url_val if "linkedin.com" in url_val else None,
            "email": extract_email(desc),
            "phone": extract_phone(desc),
            "followers": "—",
            "niche": niche,
            "source": "Google",
            "score": 65 if extract_email(desc) else 35,
            "platform": "google"
        })
    return leads

async def search_instagram(niche, max_items):
    url = "https://instagram-scraper-api2.p.rapidapi.com/v1/hashtag"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "instagram-scraper-api2.p.rapidapi.com"
    }
    params = {"hashtag": niche.replace(" ", "")}
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(url, headers=headers, params=params)
        data = res.json()
    items = data.get("data", {}).get("items", [])[:max_items]
    leads = []
    for i, item in enumerate(items):
        user = item.get("user") or {}
        bio = user.get("biography") or ""
        username = user.get("username") or ""
        leads.append({
            "id": i+1,
            "name": user.get("full_name") or username or "—",
            "handle": f"@{username}" if username else "—",
            "instaLink": f"https://instagram.com/{username}" if username else None,
            "linkedinLink": None,
            "email": extract_email(bio),
            "phone": extract_phone(bio),
            "followers": user.get("follower_count") or "—",
            "niche": niche,
            "source": "Instagram",
            "score": min(50 + (25 if extract_email(bio) else 0) + (15 if (user.get("follower_count") or 0) > 5000 else 0), 100),
            "platform": "instagram"
        })
    return leads

async def search_linkedin(niche, city, max_items):
    url = "https://linkedin-data-api.p.rapidapi.com/search-companies"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "linkedin-data-api.p.rapidapi.com"
    }
    params = {"keywords": f"{niche} {city}".strip()}
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(url, headers=headers, params=params)
        data = res.json()
    items = data.get("items", [])[:max_items]
    leads = []
    for i, item in enumerate(items):
        leads.append({
            "id": i+1,
            "name": item.get("companyName") or item.get("name") or "—",
            "handle": "—",
            "instaLink": None,
            "linkedinLink": item.get("companyLink") or item.get("url"),
            "email": extract_email(item.get("description") or ""),
            "phone": "—",
            "followers": item.get("followersCount") or "—",
            "niche": item.get("industry") or niche,
            "source": "LinkedIn",
            "score": 60,
            "platform": "linkedin"
        })
    return leads

@app.post("/api/search")
async def search_leads(req: SearchRequest):
    try:
        if req.platform == "instagram":
            leads = await search_instagram(req.niche, req.maxItems)
        elif req.platform == "linkedin":
            leads = await search_linkedin(req.niche, req.city, req.maxItems)
        else:
            leads = await search_google(req.niche, req.city, req.maxItems)
        return {"leads": leads, "total": len(leads)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def frontend():
    html_path = pathlib.Path(__file__).parent / "index.html"
    return html_path.read_text()
