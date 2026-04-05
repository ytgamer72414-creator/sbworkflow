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
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "google-search74.p.rapidapi.com",
        "Content-Type": "application/json"
    }
    params = {"query": query, "limit": str(max_items), "related_keywords": "true"}
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(url, headers=headers, params=params)
        data = res.json()
    results = data.get("results", [])
    leads = []
    for i, item in enumerate(results[:max_items]):
        desc = (item.get("description") or "") + " " + (item.get("url") or "")
        url_val = item.get("url") or ""
        name = item.get("title") or "Unknown"
        leads.append({
            "id": i+1,
            "name": name,
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

async def search_instagram(niche, city, max_items):
    # Search Instagram users by hashtag using stable API
    url = "https://instagram-scraper-stable-api.p.rapidapi.com/get_ig_user_followers_v2.php"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "instagram-scraper-stable-api.p.rapidapi.com",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    # Search for niche accounts via Google first, then get their followers
    # Use hashtag search approach
    search_url = "https://google-search74.p.rapidapi.com/"
    search_headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "google-search74.p.rapidapi.com",
        "Content-Type": "application/json"
    }
    query = f"{niche} {city} site:instagram.com".strip()
    params = {"query": query, "limit": str(max_items), "related_keywords": "true"}
    
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(search_url, headers=search_headers, params=params)
        data = res.json()
    
    results = data.get("results", [])
    leads = []
    for i, item in enumerate(results[:max_items]):
        url_val = item.get("url") or ""
        title = item.get("title") or ""
        desc = item.get("description") or ""
        
        # Extract Instagram username from URL
        username = ""
        if "instagram.com/" in url_val:
            parts = url_val.split("instagram.com/")
            if len(parts) > 1:
                username = parts[1].split("/")[0].split("?")[0]
        
        leads.append({
            "id": i+1,
            "name": title.replace(" • Instagram", "").replace(" (@", "").split(")")[0] or username or "—",
            "handle": f"@{username}" if username else "—",
            "instaLink": f"https://instagram.com/{username}" if username else url_val,
            "linkedinLink": None,
            "email": extract_email(desc),
            "phone": extract_phone(desc),
            "followers": "—",
            "niche": niche,
            "source": "Instagram",
            "score": 55 if username else 35,
            "platform": "instagram"
        })
    return leads

async def search_linkedin(niche, city, max_items):
    # Search LinkedIn via Google
    url = "https://google-search74.p.rapidapi.com/"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "google-search74.p.rapidapi.com",
        "Content-Type": "application/json"
    }
    query = f"{niche} {city} site:linkedin.com/company".strip()
    params = {"query": query, "limit": str(max_items), "related_keywords": "true"}
    
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(url, headers=headers, params=params)
        data = res.json()
    
    results = data.get("results", [])
    leads = []
    for i, item in enumerate(results[:max_items]):
        url_val = item.get("url") or ""
        desc = item.get("description") or ""
        leads.append({
            "id": i+1,
            "name": item.get("title") or "—",
            "handle": "—",
            "instaLink": None,
            "linkedinLink": url_val if "linkedin.com" in url_val else None,
            "email": extract_email(desc),
            "phone": extract_phone(desc),
            "followers": "—",
            "niche": niche,
            "source": "LinkedIn",
            "score": 60,
            "platform": "linkedin"
        })
    return leads

@app.post("/api/search")
async def search_leads(req: SearchRequest):
    try:
        if req.platform == "instagram":
            leads = await search_instagram(req.niche, req.city, req.maxItems)
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
