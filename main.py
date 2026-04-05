from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import httpx
import asyncio
import re
import os
import pathlib

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "apify_api_KLKCtXq2OKg0VzDBC9bwedjCVbMY5u4uWqgQ")

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

def parse_items(items, platform):
    if not isinstance(items, list):
        return []
    results = []
    for i, item in enumerate(items):
        if platform == "instagram":
            bio = item.get("biography") or ""
            lead = {
                "id": i+1,
                "name": item.get("fullName") or item.get("username") or "—",
                "handle": f"@{item['username']}" if item.get("username") else "—",
                "instaLink": f"https://instagram.com/{item['username']}" if item.get("username") else None,
                "linkedinLink": None,
                "email": extract_email(bio),
                "phone": extract_phone(bio),
                "followers": item.get("followersCount") or "—",
                "niche": item.get("category") or "—",
                "source": "Instagram",
                "score": min(50 + (25 if extract_email(bio) else 0) + (15 if (item.get("followersCount") or 0) > 5000 else 0), 100),
                "platform": "instagram"
            }
        elif platform == "linkedin":
            desc = item.get("description") or ""
            lead = {
                "id": i+1,
                "name": item.get("name") or item.get("companyName") or "—",
                "handle": "—",
                "instaLink": None,
                "linkedinLink": item.get("url"),
                "email": item.get("email") or extract_email(desc),
                "phone": item.get("phone") or extract_phone(desc),
                "followers": item.get("followersCount") or "—",
                "niche": item.get("industry") or "—",
                "source": "LinkedIn",
                "score": min(50 + (25 if item.get("email") else 0), 100),
                "platform": "linkedin"
            }
        else:
            desc = (item.get("description") or "") + (item.get("url") or "")
            url = item.get("url") or ""
            lead = {
                "id": i+1,
                "name": item.get("title") or "Unknown",
                "handle": "—",
                "instaLink": url if "instagram.com" in url else None,
                "linkedinLink": url if "linkedin.com" in url else None,
                "email": extract_email(desc),
                "phone": extract_phone(desc),
                "followers": "—",
                "niche": "—",
                "source": "Google",
                "score": 65 if extract_email(desc) else 35,
                "platform": "google"
            }
        if lead["name"] and lead["name"] != "—":
            results.append(lead)
    return results

@app.post("/api/search")
async def search_leads(req: SearchRequest):
    actor_map = {
        "instagram": ("apify/instagram-hashtag-scraper", {"hashtags": [req.niche.replace(" ", "")], "resultsLimit": req.maxItems}),
        "linkedin": ("curious_coder/linkedin-company-scraper", {"searchKeywords": f"{req.niche} {req.city}".strip(), "maxResults": req.maxItems}),
        "google": ("apify/google-search-scraper", {"queries": f"{req.niche} {req.city} contact email".strip(), "resultsPerPage": req.maxItems, "maxPagesPerQuery": 1})
    }
    actor_id, input_data = actor_map.get(req.platform, actor_map["google"])
    async with httpx.AsyncClient(timeout=120) as client:
        run_res = await client.post(
            f"https://api.apify.com/v2/acts/{actor_id}/runs?token={APIFY_TOKEN}",
            json={**input_data, "maxItems": req.maxItems}
        )
        run_data = run_res.json()
        if not run_data.get("data", {}).get("id"):
            raise HTTPException(status_code=500, detail=str(run_data))
        run_id = run_data["data"]["id"]
        dataset_id = run_data["data"]["defaultDatasetId"]
        for _ in range(24):
            await asyncio.sleep(5)
            st = await client.get(f"https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_TOKEN}")
            status = st.json().get("data", {}).get("status")
            if status == "SUCCEEDED":
                break
            if status in ("FAILED", "ABORTED"):
                raise HTTPException(status_code=500, detail=f"Actor {status}")
        items = (await client.get(
            f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={APIFY_TOKEN}&limit=50"
        )).json()
    leads = parse_items(items, req.platform)
    return {"leads": leads, "total": len(leads)}

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def frontend():
    html_path = pathlib.Path(__file__).parent / "index.html"
    return html_path.read_text()
