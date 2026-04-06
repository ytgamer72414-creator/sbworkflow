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

def calculate_score(lead):
    score = 0
    if lead.get("email"): score += 40
    if lead.get("phone"): score += 20
    if lead.get("name") and lead["name"] not in ["Unknown", "—"]: score += 15
    if lead.get("instaLink"): score += 10
    if lead.get("linkedinLink"): score += 10
    followers = lead.get("followers")
    if followers and followers != "—":
        try:
            f = int(str(followers).replace(",", ""))
            if f > 10000: score += 15
            elif f > 1000: score += 10
            elif f > 500: score += 5
        except: pass
    return min(score, 100)

def is_valid_instagram_url(url):
    if not url: return False
    # Must be a proper instagram profile URL not a post/reel/explore
    if not "instagram.com/" in url: return False
    path = url.split("instagram.com/")[-1].split("/")[0].split("?")[0]
    # Skip invalid paths
    invalid = ["p", "reel", "explore", "stories", "tv", "reels", "accounts", ""]
    if path in invalid: return False
    if len(path) < 2: return False
    return True

def is_valid_lead(lead):
    # Must have a real name
    if not lead.get("name") or lead["name"] in ["Unknown", "—", ""]: 
        return False
    # Must have at least one contact method or social link
    has_contact = bool(lead.get("email") or lead.get("phone"))
    has_social = bool(lead.get("instaLink") or lead.get("linkedinLink"))
    if not has_contact and not has_social:
        return False
    return True

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
        name = item.get("title") or ""
        # Clean name - remove common suffixes
        for suffix in [" - Contact Us", " | Contact", " - Home", " | Home", " - Google Maps"]:
            name = name.replace(suffix, "")
        name = name.strip()
        
        insta_link = url_val if "instagram.com/" in url_val and is_valid_instagram_url(url_val) else None
        linkedin_link = url_val if "linkedin.com/" in url_val else None
        
        lead = {
            "id": len(leads)+1,
            "name": name or "—",
            "handle": "—",
            "instaLink": insta_link,
            "linkedinLink": linkedin_link,
            "email": extract_email(desc),
            "phone": extract_phone(desc),
            "followers": "—",
            "niche": niche,
            "source": "Google",
            "platform": "google"
        }
        lead["score"] = calculate_score(lead)
        if is_valid_lead(lead):
            leads.append(lead)
    return leads

async def search_instagram(niche, city, max_items):
    key = get_key()
    search_url = "https://google-search74.p.rapidapi.com/"
    headers = {
        "x-rapidapi-key": key,
        "x-rapidapi-host": "google-search74.p.rapidapi.com",
        "Content-Type": "application/json"
    }
    query = f"{niche} {city} instagram.com profile".strip()
    params = {"query": query, "limit": str(max_items * 2), "related_keywords": "true"}

    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(search_url, headers=headers, params=params)
        data = res.json()

    results = data.get("results", [])
    leads = []
    seen_usernames = set()
    
    for item in results:
        if len(leads) >= max_items:
            break
            
        url_val = item.get("url") or ""
        title = item.get("title") or ""
        desc = item.get("description") or ""

        # Only process valid Instagram profile URLs
        if not is_valid_instagram_url(url_val):
            continue

        username = url_val.split("instagram.com/")[-1].split("/")[0].split("?")[0].strip()
        
        # Skip duplicates
        if username in seen_usernames:
            continue
        seen_usernames.add(username)

        # Clean name properly
        clean_name = title
        for suffix in [" • Instagram photos and videos", " • Instagram", 
                       f" (@{username})", f"(@{username})", username,
                       "- Instagram", "| Instagram"]:
            clean_name = clean_name.replace(suffix, "")
        clean_name = clean_name.strip(" |-•")

        lead = {
            "id": len(leads)+1,
            "name": clean_name or username,
            "handle": f"@{username}",
            "instaLink": f"https://instagram.com/{username}",
            "linkedinLink": None,
            "email": extract_email(desc),
            "phone": extract_phone(desc),
            "followers": "—",
            "niche": niche,
            "source": "Instagram",
            "platform": "instagram"
        }
        lead["score"] = calculate_score(lead)
        if is_valid_lead(lead):
            leads.append(lead)
    return leads

async def search_linkedin(niche, city, max_items):
    key = get_key()
    url = "https://google-search74.p.rapidapi.com/"
    headers = {
        "x-rapidapi-key": key,
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
        name = item.get("title") or ""
        for suffix in [" | LinkedIn", "- LinkedIn", " - Overview | LinkedIn"]:
            name = name.replace(suffix, "")
        name = name.strip()
        
        lead = {
            "id": len(leads)+1,
            "name": name or "—",
            "handle": "—",
            "instaLink": None,
            "linkedinLink": url_val if "linkedin.com" in url_val else None,
            "email": extract_email(desc),
            "phone": extract_phone(desc),
            "followers": "—",
            "niche": niche,
            "source": "LinkedIn",
            "platform": "linkedin"
        }
        lead["score"] = calculate_score(lead)
        if is_valid_lead(lead):
            leads.append(lead)
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
        # Sort by score descending
        leads = sorted(leads, key=lambda x: x["score"], reverse=True)
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
