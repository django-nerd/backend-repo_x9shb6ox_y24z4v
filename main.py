import os
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Coaching, Note

# For basic crawling
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlparse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Coaching Leads API"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response

# Helpers
class CoachingFilter(BaseModel):
    city: Optional[str] = None
    exams: Optional[List[str]] = None
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    status: Optional[str] = None  # liked, disliked, neutral


def to_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")


# Coaching Endpoints
@app.post("/coaching", response_model=dict)
async def create_coaching(item: Coaching):
    inserted_id = create_document("coaching", item)
    return {"id": inserted_id}

@app.get("/coachings")
async def list_coachings(city: Optional[str] = None, exams: Optional[str] = None, min_size: Optional[int] = None, max_size: Optional[int] = None, status: Optional[str] = None, q: Optional[str] = None):
    filt = {}
    if city:
        filt["city"] = {"$regex": f"^{city}$", "$options": "i"}
    if status:
        filt["status"] = status
    if exams:
        # exams comma-separated
        exams_list = [e.strip() for e in exams.split(',') if e.strip()]
        if exams_list:
            filt["exams"] = {"$all": exams_list}
    if min_size is not None or max_size is not None:
        range_cond = {}
        if min_size is not None:
            range_cond["$gte"] = min_size
        if max_size is not None:
            range_cond["$lte"] = max_size
        filt["size"] = range_cond
    if q:
        filt["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"address": {"$regex": q, "$options": "i"}},
            {"city": {"$regex": q, "$options": "i"}},
        ]

    docs = get_documents("coaching", filt)
    # Convert ObjectId
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return {"items": docs}

@app.get("/coaching/{coaching_id}")
async def get_coaching(coaching_id: str):
    oid = to_object_id(coaching_id)
    doc = db["coaching"].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    doc["id"] = str(doc.pop("_id"))
    return doc

class UpdateStatus(BaseModel):
    status: str

@app.post("/coaching/{coaching_id}/status")
async def update_status(coaching_id: str, payload: UpdateStatus):
    if payload.status not in ["liked", "disliked", "neutral"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    oid = to_object_id(coaching_id)
    db["coaching"].update_one({"_id": oid}, {"$set": {"status": payload.status, "updated_at": time.time()}})
    return {"ok": True}

# Notes Endpoints
@app.post("/coaching/{coaching_id}/notes")
async def add_note(coaching_id: str, payload: Note):
    if payload.coaching_id != coaching_id:
        # ensure consistency
        payload.coaching_id = coaching_id
    note_id = create_document("note", payload)
    return {"id": note_id}

@app.get("/coaching/{coaching_id}/notes")
async def list_notes(coaching_id: str):
    docs = get_documents("note", {"coaching_id": coaching_id})
    for d in docs:
        d["id"] = str(d.pop("_id"))
    # sort by created_at desc if present
    docs.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return {"items": docs}

# Simple AI agent stub (will call external API via requests if API key present)
class AgentQuery(BaseModel):
    query: str

@app.post("/coaching/{coaching_id}/agent")
async def coaching_agent(coaching_id: str, payload: AgentQuery):
    # Basic stub: echo + suggest actions based on fields
    coaching = db["coaching"].find_one({"_id": to_object_id(coaching_id)})
    if not coaching:
        raise HTTPException(status_code=404, detail="Coaching not found")
    name = coaching.get("name", "this coaching")
    city = coaching.get("city", "the city")
    exams = ", ".join(coaching.get("exams", [])[:5]) or "multiple exams"
    suggestions = [
        f"Research recent reviews of {name} on Google and Reddit.",
        f"Check LinkedIn for alumni or staff from {name} in {city}.",
        f"Look for photo galleries and infrastructure details if targeting {exams}.",
        "Draft an email introducing your services with 2-3 tailored benefits.",
        "Schedule a follow-up reminder in 3 days if no response.",
    ]
    response = {
        "answer": f"You asked: '{payload.query}'. For {name} in {city}, consider: ",
        "suggestions": suggestions
    }
    return response

# Basic web crawling to fetch coachings based on filters
class CrawlRequest(BaseModel):
    city: str
    exams: Optional[List[str]] = None
    limit: int = 20


def _ddg_search_urls(query: str, limit: int = 20) -> List[str]:
    # DuckDuckGo HTML endpoint
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        r = requests.get(url, timeout=12, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36"
        })
        r.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(r.text, 'html.parser')
    links = []
    for a in soup.select('a.result__a'):
        href = a.get('href')
        if href and href.startswith('http'):
            links.append(href)
        if len(links) >= limit:
            break
    # Fallback selector
    if not links:
        for a in soup.find_all('a'):
            href = a.get('href')
            if href and href.startswith('http'):
                links.append(href)
            if len(links) >= limit:
                break
    # Deduplicate same domains
    seen = set()
    uniq = []
    for l in links:
        dom = urlparse(l).netloc
        if dom not in seen:
            seen.add(dom)
            uniq.append(l)
        if len(uniq) >= limit:
            break
    return uniq


def _extract_basic_page_info(link: str):
    info = {"name": None, "address": None, "phone": None, "website": None, "google_maps_url": None, "description": None}
    info["website"] = link if 'google.' not in link else None
    if 'google.com/maps' in link or 'goo.gl/maps' in link:
        info["google_maps_url"] = link
    try:
        r = requests.get(link, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36"
        })
        # some sites block scraping; proceed best-effort
        html = r.text
        soup = BeautifulSoup(html, 'html.parser')
        title = soup.title.string.strip() if soup.title and soup.title.string else None
        if title:
            info["name"] = title[:120]
        desc = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
        if desc and desc.get('content'):
            info["description"] = desc.get('content')[:300]
        og_title = soup.find('meta', attrs={'property': 'og:title'})
        if og_title and og_title.get('content'):
            info["name"] = og_title.get('content')[:120]
        tel = soup.find('a', href=lambda h: h and h.startswith('tel:'))
        if tel:
            info["phone"] = tel.get('href').replace('tel:', '').strip()
    except Exception:
        pass
    return info


@app.post("/crawl")
async def crawl_and_ingest(payload: CrawlRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    city = payload.city.strip()
    if not city:
        raise HTTPException(status_code=400, detail="City is required")
    exams = payload.exams or []

    # Build query variants
    base_terms = [
        f"coaching institute {city}",
        f"tuition classes {city}",
        f"test prep coaching {city}"
    ]
    for ex in exams:
        base_terms.append(f"{ex} coaching {city}")
        base_terms.append(f"{ex} classes {city}")

    collected = []
    for q in base_terms[:5]:  # keep it light
        urls = _ddg_search_urls(q, limit=max(5, payload.limit//2))
        for u in urls:
            if u not in collected:
                collected.append(u)
            if len(collected) >= payload.limit:
                break
        if len(collected) >= payload.limit:
            break

    created = 0
    seen_keys = set()
    for link in collected:
        info = _extract_basic_page_info(link)
        key = (info.get("name") or link)[:120].lower()
        if key in seen_keys:
            continue
        seen_keys.add(key)

        doc = {
            "name": info.get("name") or (urlparse(link).netloc.replace('www.', '').split('.')[0].title() + " Coaching"),
            "city": city,
            "exams": exams,
            "size": None,
            "address": info.get("address"),
            "phone": info.get("phone"),
            "website": info.get("website"),
            "google_maps_url": info.get("google_maps_url"),
            "images": [],
            "location": None,
            "description": info.get("description"),
            "status": "neutral",
        }
        # Deduplicate against DB by website or name+city
        exists = None
        if doc["website"]:
            exists = db["coaching"].find_one({"website": doc["website"]})
        if not exists:
            exists = db["coaching"].find_one({"name": {"$regex": f"^{doc['name']}$", "$options": "i"}, "city": {"$regex": f"^{city}$", "$options": "i"}})
        if exists:
            continue
        try:
            db["coaching"].insert_one(doc)
            created += 1
        except Exception:
            continue

    return {"ok": True, "created": created, "scanned": len(collected)}

# Schema exposure for UI builders
@app.get("/schema")
async def get_schema_info():
    return {
        "collections": [
            "coaching", "note"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
