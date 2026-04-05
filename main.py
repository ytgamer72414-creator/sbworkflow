from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import httpx
import re
import os
import pathlib
import random

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Two API keys - load balancing for double requests
RAPIDAPI_KEYS = [
    os.environ.get("RAPIDAPI_KEY1", "d3fd1e720fmsh6ff53a31e928ecdp19fa06jsn4d98e98c079c"),
    os.environ.get("RAPIDAPI_KEY2", "6d7a7ca576msh6da794f299e2fb1p12c27ajsne4e021e54882"),
]

def get_key():
    return random.choice(RAPIDAPI_KEYS)

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
    key = get_key()
    query = f"{niche} {city} contact email".strip()
    url = "https://google-search74.p.rapidapi.com/"
    headers = {
        "x-rapidapi-key": key,
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

async def search_instagram(niche, city, max_items):
    key = get_key()
    # Search Instagram accounts via Google
    search_url = "https://google-search74.p.rapidapi.com/"
    headers = {
        "x-rapidapi-key": key,
        "x-rapidapi-host": "google-search74.p.rapidapi.com",
        "Content-Type": "application/json"
    }
    query = f"{niche} {city} site:instagram.com".strip()
    params = {"query": query, "limit": str(max_items), "related_keywords": "true"}

    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(search_url, headers=headers, params=params)
        data = res.json()

    results = data.get("results", [])
    leads = []
    for i, item in enumerate(results[:max_items]):
        url_val = item.get("url") or ""
        title = item.get("title") or ""
        desc = item.get("description") or ""

        username = ""
        if "instagram.com/" in url_val:
            parts = url_val.split("instagram.com/")
            if len(parts) > 1:
                username = parts[1].split("/")[0].split("?")[0]

        # Clean name - remove username and Instagram suffix
        clean_name = title
        for suffix in [" • Instagram", " (@" + username + ")", username, "- Instagram"]:
            clean_name = clean_name.replace(suffix, "")
        clean_name = clean_name.strip()

        leads.append({
            "id": i+1,
            "name": clean_name or username or "—",
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
    key = get_key()
    url = "https://realtime-linkdin-data-scraper.p.rapidapi.com/postSearch.php"
    headers = {
        "x-rapidapi-key": key,
        "x-rapidapi-host": "realtime-linkdin-data-scraper.p.rapidapi.com",
        "Content-Type": "application/json"
    }
    search_term = f"{niche} {city}".strip()
    params = {"searchTerm": search_term}

    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(url, headers=headers, params=params)
        data = res.json()

    # Handle LinkedIn response
    print("LinkedIn raw response:", data)
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("data", []) or data.get("results", []) or data.get("items", [])

    leads = []
    for i, item in enumerate(items[:max_items]):
        desc = (item.get("description") or item.get("text") or item.get("summary") or "")
        author = item.get("author") or item.get("name") or item.get("companyName") or "—"
        linkedin_url = item.get("url") or item.get("postUrl") or item.get("profileUrl") or ""

        leads.append({
            "id": i+1,
            "name": author,
            "handle": "—",
            "instaLink": None,
            "linkedinLink": linkedin_url if "linkedin.com" in linkedin_url else None,
            "email": extract_email(desc),
            "phone": extract_phone(desc),
            "followers": item.get("followersCount") or "—",
            "niche": niche,
            "source": "LinkedIn",
            "score": 65 if extract_email(desc) else 50,
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
