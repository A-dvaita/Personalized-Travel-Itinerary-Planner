"""
Personalized Travel Itinerary Planner  -  Skill Wallet Capstone Project 4
=========================================================================
Single-file, zero-database Streamlit app (deploys 1-click on Streamlit Community Cloud).

Sections
  1. Constants & curated demo knowledge base
  2. Helpers (state, money, text)
  3. LLM layer (Gemini / Groq over REST)  +  AI prompts
  4. Demo engine (offline, geographic-cluster based)
  5. Persistence (simulated DB: session + JSON file per workspace)
  6. PDF export (reportlab)
  7. UI (CSS, sidebar, preferences, 4 tabs)
"""
from __future__ import annotations

import copy
import html
import io
import json
import re
import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Wanderlust | Travel Itinerary Planner", page_icon="🧭", layout="wide")
ss = st.session_state

# ════════════════════════════════════════════════════════════════════════════
# 1. CONSTANTS & DEMO KNOWLEDGE BASE
# ════════════════════════════════════════════════════════════════════════════
SLOTS = ["Morning Sightseeing", "Lunch Recommendation", "Afternoon Leisure", "Evening Dining & Entertainment"]
SLOT_SHORT = ["Morning", "Lunch", "Afternoon", "Evening"]
SLOT_KEYS = ["m", "l", "a", "e"]
SLOT_ICON = ["🌅", "🍽️", "🌴", "🌙"]
PACE_TIMES = {"Relaxed": ["10:00", "13:30", "16:00", "19:30"],
              "Moderate": ["09:00", "13:00", "15:30", "19:00"],
              "Fast-Paced": ["07:30", "12:30", "14:00", "18:30"]}
PACE_TAGS = {"Relaxed": {"relax"}, "Moderate": set(), "Fast-Paced": {"adventure"}}
BUDGET_MULT = {"Budget": 0.6, "Moderate": 1.0, "Luxury": 1.9}
DAILY_REF_USD = {"Budget": 45, "Moderate": 100, "Luxury": 250}  # food + activities, per person / day
VIBES = ["Beach", "Mountains", "Cultural", "Urban"]
INTERESTS = ["Food", "Adventure", "History", "Nightlife"]
INTEREST_TAGS = {"Food": {"food"}, "Adventure": {"adventure", "outdoor"},
                 "History": {"history", "museum", "culture"}, "Nightlife": {"nightlife"}}
VIBE_TAGS = {"Beach": {"beach", "relax"}, "Mountains": {"outdoor", "adventure"},
             "Cultural": {"culture", "history"}, "Urban": {"market", "shopping", "food"}}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# Approximate local-currency units per 1 USD (INR is driven by the sidebar rate). Editable in code.
FX = {"USD": 1.0, "EUR": 0.92, "GBP": 0.78, "JPY": 150.0, "IDR": 16000.0, "THB": 35.0, "AED": 3.67,
      "CHF": 0.88, "SGD": 1.3, "AUD": 1.5, "CAD": 1.37, "MYR": 4.4, "VND": 25000.0, "MXN": 18.0}
EMERGENCY = {
    "India": [("Police / all emergencies", "112"), ("Ambulance", "108"), ("Tourist helpline", "1363")],
    "France": [("All emergencies (EU)", "112"), ("Medical (SAMU)", "15"), ("Police", "17")],
    "Japan": [("Police", "110"), ("Fire / Ambulance", "119"), ("Japan Visitor Hotline", "050-3816-2787")],
    "Indonesia": [("Police", "110"), ("Ambulance", "118 / 119"), ("Search & Rescue", "115")],
}
TAG_DESC = {"history": "Step into local history", "food": "A flavour-packed stop", "outdoor": "Fresh air and scenery",
            "relax": "Unhurried and restful", "adventure": "A shot of adrenaline", "nightlife": "Lively after-dark energy",
            "market": "Browse stalls and crafts", "museum": "Absorbing indoor exploration", "culture": "Local traditions up close",
            "beach": "Sand, sea and sunshine", "veg": "Vegetarian-friendly", "shopping": "Souvenir hunting",
            "seafood": "Fresh-catch specialities", "indoor": "Weather-proof"}
TIPS = ["Arrive early to beat the crowds and the heat.", "Carry small change and confirm opening hours.",
        "Keep this slot flexible - swim, rest or wander.", "Reserve ahead for popular spots; check dress codes."]
KEYWORDS = {"museum": "museum", "museums": "museum", "market": "market", "markets": "market", "outdoor": "outdoor",
            "outdoors": "outdoor", "vegetarian": "veg", "veg": "veg", "vegan": "veg", "beach": "beach",
            "nightlife": "nightlife", "party": "nightlife", "bar": "nightlife", "food": "food", "seafood": "seafood",
            "relax": "relax", "relaxing": "relax", "chill": "relax", "quiet": "relax", "adventure": "adventure",
            "adventurous": "adventure", "thrill": "adventure", "history": "history", "historic": "history",
            "culture": "culture", "cultural": "culture", "local": "culture", "shopping": "shopping",
            "indoor": "indoor", "cheap": "__cheap", "cheaper": "__cheap", "budget": "__cheap", "affordable": "__cheap"}
QUICK = ["Swap museum for outdoor market", "Find vegetarian lunch spot", "Something more relaxing",
         "More adventurous", "Cheaper option", "Add some nightlife", "More local culture", "Custom request..."]
DAY_VIBES = {"Foodie": ({"food"}, set()), "Adventurous": ({"adventure", "outdoor"}, set()), "Relaxed": ({"relax"}, set()),
             "Cultural": ({"culture", "history"}, set()), "Nightlife": ({"nightlife"}, set()),
             "Family-friendly": (set(), {"nightlife"}), "Budget-savvy": ({"__cheap"}, set())}


def _c(area, m, l, a, e):
    return (area, {"m": m, "l": l, "a": a, "e": e})


# item = (name, cost per person in local currency at "Moderate" level, tags). Clusters are listed in route order.
CITIES = {
    "Goa": dict(country="India", cur="INR", vibes=["Beach"], months=[11, 12, 1, 2, 3], tier=1,
                fit={"Food", "Nightlife", "Adventure"}, tags=["🏖️ Golden beaches", "🦐 Seafood shacks", "🎶 Beach parties"],
                blurb="Sun, sand and Portuguese-era lanes.", clusters=[
        _c("North Goa (Baga-Anjuna)",
           [("Fort Aguada & Sinquerim sunrise walk", 100, "history outdoor"), ("Chapora Fort & Vagator cliffs", 0, "history outdoor")],
           [("Seafood thali at a Baga beach shack", 1200, "food seafood"), ("Veg-friendly cafe lunch, Anjuna", 700, "food veg relax")],
           [("Calangute beach time & parasailing", 1500, "beach adventure outdoor"), ("Anjuna flea market stroll", 500, "market shopping outdoor")],
           [("Vagator sunset & beach-shack dinner", 1500, "food relax outdoor"), ("Baga nightlife strip", 2000, "nightlife")]),
        _c("Old Goa & Panjim",
           [("Basilica of Bom Jesus & Se Cathedral", 0, "history culture"), ("Fontainhas Latin Quarter heritage walk", 0, "history culture outdoor")],
           [("Goan fish-curry rice in Panjim", 600, "food seafood"), ("Pure-veg thali in Panjim", 400, "food veg")],
           [("Reis Magos Fort & Mandovi riverfront", 100, "history outdoor"), ("Panjim municipal market browse", 300, "market shopping")],
           [("Mandovi sunset dinner cruise", 800, "relax food"), ("Live Goan music dinner, Panjim", 1800, "food nightlife culture")]),
        _c("South Goa (Palolem-Agonda)",
           [("Palolem kayaking at sunrise", 800, "adventure outdoor beach"), ("Cabo de Rama Fort", 0, "history outdoor")],
           [("Beachfront seafood, Palolem", 1000, "food seafood"), ("Veg cafe lunch, Agonda", 600, "food veg relax")],
           [("Butterfly Beach boat trip", 1000, "outdoor relax beach"), ("Spice plantation tour & tasting", 600, "culture food outdoor")],
           [("Silent-disco beach night, Palolem", 1500, "nightlife"), ("Candle-lit beach dinner, Agonda", 1800, "food relax")]),
    ]),
    "Jaipur": dict(country="India", cur="INR", vibes=["Cultural", "Urban"], months=[10, 11, 12, 1, 2, 3], tier=1,
                   fit={"History", "Food"}, tags=["🏰 Forts & palaces", "🛍️ Bazaars", "🍛 Rajasthani thali"],
                   blurb="The Pink City: palaces, bazaars and royal flavours.", clusters=[
        _c("Amer & Nahargarh (North)",
           [("Amer Fort at opening time", 550, "history culture"), ("Nahargarh Fort sunrise", 200, "history outdoor")],
           [("Rajasthani thali near Amer", 600, "food veg"), ("Lakeview cafe lunch near Jal Mahal", 500, "food relax")],
           [("Jaigarh Fort & cannon foundry", 200, "history"), ("Panna Meena stepwell & Jal Mahal view", 50, "history outdoor")],
           [("Nahargarh sunset with snacks", 600, "relax outdoor food"), ("Haveli folk-music dinner", 1500, "food culture nightlife")]),
        _c("Old City (Pink City)",
           [("City Palace & Jantar Mantar", 700, "history culture museum"), ("Hawa Mahal & Johari Bazaar walk", 200, "history market")],
           [("Pure-veg lunch at LMB", 500, "food veg"), ("Dal-baati-churma at an Old City eatery", 450, "food veg")],
           [("Bapu & Johari Bazaar shopping", 1500, "market shopping"), ("Albert Hall Museum", 40, "museum culture indoor")],
           [("Rooftop dinner facing Hawa Mahal", 1500, "food relax"), ("Evening film at Raj Mandir", 300, "culture nightlife")]),
        _c("Modern Jaipur (South)",
           [("Birla Mandir & Moti Doongri", 0, "culture outdoor"), ("Jawahar Kala Kendra art centre", 50, "museum culture")],
           [("Cafe lunch at Tapri Central", 500, "food veg"), ("Street-food crawl: kachori & lassi", 300, "food veg market")],
           [("Sanganer block-printing workshop", 800, "culture shopping"), ("Sisodia Rani Garden", 50, "relax outdoor")],
           [("Folk show & dinner, Chokhi Dhani", 1500, "food culture nightlife"), ("Craft-beer lounge, C-Scheme", 1800, "nightlife")]),
    ]),
    "Manali": dict(country="India", cur="INR", vibes=["Mountains"], months=[3, 4, 5, 6, 9, 10, 12, 1, 2], tier=1,
                   fit={"Adventure", "Food"}, tags=["🏔️ Himalayan views", "🪂 Paragliding", "❄️ Snow play"],
                   blurb="Deodar forests, river valleys and snow passes.", clusters=[
        _c("Old Manali & Vashisht",
           [("Manu Temple & Old Manali walk", 0, "culture outdoor"), ("Vashisht hot springs & temple", 50, "culture relax")],
           [("Riverside cafe lunch, Old Manali", 700, "food veg relax"), ("Himachali dham tasting", 500, "food")],
           [("Jogini Falls hike", 0, "adventure outdoor"), ("Beas river rafting (seasonal)", 1500, "adventure outdoor")],
           [("Live-music cafes, Old Manali", 1200, "nightlife food"), ("Riverside bonfire dinner", 1500, "relax food")]),
        _c("Mall Road & Hadimba",
           [("Hadimba Temple & cedar forest", 0, "culture history outdoor"), ("Himachal Cultural Museum", 50, "museum culture indoor")],
           [("Tibetan momos & thukpa", 400, "food veg"), ("Trout lunch by the river", 900, "food")],
           [("Mall Road & Tibetan monastery", 500, "market shopping culture"), ("Van Vihar picnic", 100, "relax outdoor")],
           [("Rooftop dinner on Mall Road", 1000, "food"), ("Cafe music night", 800, "nightlife")]),
        _c("Solang & Atal Tunnel (North)",
           [("Solang Valley paragliding", 3000, "adventure outdoor"), ("Atal Tunnel & Sissu village drive", 1500, "outdoor adventure")],
           [("Dhaba lunch in Solang", 400, "food veg"), ("Picnic lunch at Sissu", 500, "food relax")],
           [("Snow activities at Solang", 1200, "adventure outdoor"), ("Quad biking & zorbing", 1500, "adventure outdoor")],
           [("Cosy homestay dinner", 800, "food relax"), ("Campfire stargazing", 1000, "relax outdoor")]),
    ]),
    "Paris": dict(country="France", cur="EUR", vibes=["Cultural", "Urban"], months=[4, 5, 6, 9, 10], tier=3,
                  fit={"Food", "History", "Nightlife"}, tags=["🗼 Iconic landmarks", "🥐 Cafe culture", "🎨 World-class museums"],
                  blurb="Art, boulevards and bistros on the Seine.", clusters=[
        _c("Eiffel & West Paris",
           [("Eiffel Tower summit", 29, "history outdoor"), ("Musee d'Orsay", 16, "museum culture indoor")],
           [("Cafe on Rue Cler market street", 22, "food veg market"), ("Bistro lunch near Les Invalides", 28, "food")],
           [("Champ de Mars & Seine stroll", 0, "relax outdoor"), ("Musee Rodin gardens", 14, "museum relax outdoor")],
           [("Seine dinner cruise", 70, "food relax"), ("Trocadero sunset & wine bar", 35, "nightlife relax")]),
        _c("Louvre - Ile de la Cite - Latin Quarter",
           [("Louvre Museum", 22, "museum culture history indoor"), ("Sainte-Chapelle & Notre-Dame exterior", 20, "history culture")],
           [("Falafel & crepes in Le Marais", 14, "food veg market"), ("Classic bistro, Latin Quarter", 30, "food")],
           [("Tuileries & Luxembourg Gardens", 0, "relax outdoor"), ("Shakespeare & Co. and Latin Quarter walk", 0, "culture relax")],
           [("Jazz club in Saint-Germain", 30, "nightlife culture"), ("Dinner in Le Marais", 45, "food")]),
        _c("Montmartre & North",
           [("Sacre-Coeur & Place du Tertre", 0, "history culture outdoor"), ("Musee de Montmartre", 15, "museum culture")],
           [("Creperie lunch in Montmartre", 18, "food veg"), ("Bistro at Abbesses", 25, "food")],
           [("Saint-Ouen flea market", 0, "market shopping outdoor"), ("Canal Saint-Martin picnic", 15, "relax outdoor")],
           [("Moulin Rouge show", 95, "nightlife culture"), ("Cabaret evening at Lapin Agile", 35, "nightlife culture")]),
    ]),
    "Tokyo": dict(country="Japan", cur="JPY", vibes=["Urban", "Cultural"], months=[3, 4, 5, 10, 11], tier=2,
                  fit={"Food", "Nightlife", "History"}, tags=["🍣 Sushi & ramen", "🌸 Cherry blossoms", "🌃 Neon nightlife"],
                  blurb="Temples, tech and the world's best food scene.", clusters=[
        _c("Asakusa - Ueno (East)",
           [("Senso-ji Temple & Nakamise street", 0, "history culture"), ("Ueno Park & Tokyo National Museum", 1000, "museum culture outdoor")],
           [("Tempura lunch in Asakusa", 1800, "food"), ("Shojin-style vegetarian lunch, Ueno", 2200, "food veg")],
           [("Sumida River cruise & Skytree", 2100, "relax outdoor"), ("Ameyoko market, Ueno", 1500, "market shopping food")],
           [("Izakaya crawl in Asakusa", 4000, "food nightlife"), ("Ramen dinner near Kappabashi", 1200, "food")]),
        _c("Ginza - Tsukiji - Odaiba (Bay)",
           [("Tsukiji Outer Market breakfast", 2500, "food market"), ("Hama-rikyu Gardens", 300, "relax outdoor history")],
           [("Sushi counter in Ginza", 5000, "food"), ("Veggie ramen near Tokyo Station", 1400, "food veg")],
           [("teamLab Planets", 3800, "culture indoor"), ("Ginza shopping & Kabuki-za", 2000, "shopping culture")],
           [("Odaiba waterfront dinner", 3000, "food relax"), ("Single-act Kabuki evening", 2000, "culture")]),
        _c("Shibuya - Harajuku - Shinjuku (West)",
           [("Meiji Shrine & Yoyogi Park", 0, "history culture outdoor"), ("Shinjuku Gyoen garden", 500, "relax outdoor")],
           [("Ramen in Shinjuku", 1200, "food"), ("Vegan crepes & cafes, Harajuku", 1500, "food veg")],
           [("Takeshita Street & Omotesando", 1500, "shopping culture"), ("Shibuya Sky rooftop", 2200, "outdoor relax")],
           [("Golden Gai bar hopping", 4000, "nightlife food"), ("Shibuya Crossing & karaoke", 3500, "nightlife")]),
    ]),
    "Bali": dict(country="Indonesia", cur="IDR", vibes=["Beach", "Cultural"], months=[4, 5, 6, 7, 8, 9], tier=1,
                 fit={"Adventure", "Food"}, tags=["🌴 Rice terraces", "🧘 Wellness", "🏄 Surf breaks"],
                 blurb="Temples, terraces and surf on the Island of the Gods.", clusters=[
        _c("Ubud (Central)",
           [("Tegalalang rice terraces", 25000, "outdoor culture"), ("Sacred Monkey Forest", 100000, "outdoor culture")],
           [("Warung nasi campur lunch", 70000, "food"), ("Vegan lunch at an Ubud cafe", 90000, "food veg")],
           [("Tirta Empul water temple", 50000, "culture history"), ("Balinese cooking class", 450000, "food culture")],
           [("Legong dance at Ubud Palace", 120000, "culture nightlife"), ("Dinner overlooking rice fields", 250000, "food relax")]),
        _c("Seminyak - Canggu (West Coast)",
           [("Canggu surf lesson", 350000, "adventure beach outdoor"), ("Tanah Lot temple", 75000, "history culture outdoor")],
           [("Smoothie-bowl cafe, Canggu", 100000, "food veg"), ("Warung lunch in Seminyak", 90000, "food")],
           [("Beach club afternoon, Seminyak", 300000, "relax beach"), ("Petitenget Beach & boutiques", 150000, "shopping relax")],
           [("Echo Beach sunset dinner", 300000, "food relax"), ("Jalan Legian nightlife", 400000, "nightlife")]),
        _c("Uluwatu & Bukit (South)",
           [("Uluwatu Temple & cliff walk", 50000, "culture outdoor"), ("Padang Padang & Bingin beaches", 20000, "beach outdoor")],
           [("Cliffside cafe lunch", 150000, "food relax"), ("Vegetarian warung, Pecatu", 80000, "food veg")],
           [("Dreamland Beach & surfing", 200000, "beach adventure"), ("Blue Point cave swim", 100000, "outdoor adventure")],
           [("Kecak fire dance at sunset", 150000, "culture nightlife"), ("Jimbaran Beach seafood dinner", 350000, "food seafood relax")]),
    ]),
}


# ════════════════════════════════════════════════════════════════════════════
# 2. HELPERS
# ════════════════════════════════════════════════════════════════════════════
class LLMError(Exception):
    """Raised for any recoverable AI-layer failure (callers fall back to the demo engine)."""


def esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def init_state():
    defaults = {"f_dest": "", "f_vibe": "Beach", "f_days": 5, "f_start": date.today() + timedelta(days=30),
                "f_budget": "Moderate", "f_party": "Couple", "f_trav": 2, "f_pace": "Moderate",
                "f_interests": ["Food", "History"], "f_veg": False, "f_notes": "",
                "demo": True, "provider": "Gemini", "api_key": "", "m_gemini": "gemini-3.8-flash",
                "m_groq": "llama-3.3-70b-versatile", "usd_inr": 88.0, "workspace": uuid.uuid4().hex[:6],
                "itin": None, "recs": None, "undo": [], "log": [], "active_trip": None, "picked": None, "last_import": None}
    for k, v in defaults.items():
        ss.setdefault(k, v)


def get_prefs() -> dict:
    return dict(destination=ss.f_dest.strip(), vibe=ss.f_vibe, days=int(ss.f_days), start=ss.f_start,
                budget=ss.f_budget, party=ss.f_party, travellers=int(ss.f_trav), pace=ss.f_pace,
                interests=list(ss.f_interests), vegetarian=bool(ss.f_veg), notes=ss.f_notes.strip())


def serial_prefs(p: dict) -> dict:
    return {**p, "start": p["start"].isoformat() if isinstance(p["start"], date) else p["start"]}


def itin_prefs(itin: dict) -> dict:
    p = dict(itin["prefs"])
    p["start"] = date.fromisoformat(p["start"]) if isinstance(p["start"], str) else p["start"]
    return p


def match_city(name: str):
    n = (name or "").strip().lower()
    for c in CITIES:
        if n and (n in c.lower() or c.lower() in n):
            return c
    return None


def fmt_date(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%a, %d %b %Y")


def conv(itin: dict, amt: float):
    """Local amount -> (USD, INR); None where the currency is unknown."""
    cur, rate = itin["currency"], float(ss.usd_inr)
    if cur == "INR":
        return amt / rate, amt
    lpu = FX.get(cur) or itin.get("local_per_usd")
    if cur == "USD":
        lpu = 1.0
    if not lpu:
        return None, None
    usd = amt / lpu
    return usd, usd * rate


def trio(itin: dict, amt: float) -> str:
    usd, inr = conv(itin, amt)
    base = f"{itin['currency']} {amt:,.0f}"
    return base if usd is None else f"{base} · ${usd:,.0f} · ₹{inr:,.0f}"


def itin_total(itin: dict) -> float:
    return sum(float(s["cost_local"]) for d in itin["days"] for s in d["slots"])


def day_total(day: dict) -> float:
    return sum(float(s["cost_local"]) for s in day["slots"])


def backtracking(itin: dict) -> int:
    seen, prev, bt = set(), None, 0
    for d in itin["days"]:
        if d["area"] != prev:
            bt += d["area"] in seen
            seen.add(d["area"])
            prev = d["area"]
    return bt


def push_undo(note: str):
    ss.undo.append(copy.deepcopy(ss.itin))
    ss.undo = ss.undo[-10:]
    ss.log.insert(0, f"{datetime.now():%H:%M} - {note}")


# ════════════════════════════════════════════════════════════════════════════
# 3. LLM LAYER
# ════════════════════════════════════════════════════════════════════════════
def secret_key(provider: str) -> str:
    try:
        return str(st.secrets.get(f"{provider.upper()}_API_KEY", ""))
    except Exception:
        return ""


def current_key() -> str:
    return (ss.api_key or "").strip() or secret_key(ss.provider)


def ai_enabled() -> bool:
    return (not ss.demo) and bool(current_key())


def call_llm(system: str, user: str, temperature: float = 0.6) -> dict:
    provider, key = ss.provider, current_key()
    model = ss.m_gemini if provider == "Gemini" else ss.m_groq
    try:
        if provider == "Gemini":
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json={"systemInstruction": {"parts": [{"text": system}]},
                      "contents": [{"role": "user", "parts": [{"text": user}]}],
                      "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"}},
                timeout=90)
        else:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "temperature": temperature, "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                timeout=90)
        if r.status_code != 200:
            raise LLMError(f"{provider} returned HTTP {r.status_code}: {r.text[:160].replace(key, '***')}")
        data = r.json()
        text = (data["candidates"][0]["content"]["parts"][0]["text"] if provider == "Gemini"
                else data["choices"][0]["message"]["content"])
        return parse_json(text)
    except LLMError:
        raise
    except requests.RequestException as e:
        raise LLMError(f"Network error: {str(e).replace(key, '***')[:160]}")
    except (KeyError, IndexError, ValueError) as e:
        raise LLMError(f"Unexpected AI response ({type(e).__name__})")


def parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        if a >= 0 < b:
            return json.loads(text[a:b + 1])
        raise


SYS = "You are a meticulous senior travel planner. Reply with ONE valid JSON object only - no markdown, no commentary."
SLOT_SCHEMA = ('{"slot":"<slot name>","title":"<real place/activity>","area":"<neighbourhood>","description":"<1-2 sentences>",'
               '"cost_local":<number, TOTAL for whole party in local currency>,"tags":["food","outdoor"],"tip":"<short tip>"}')


def profile(p: dict) -> str:
    return (f"party={p['party']} ({p['travellers']} travellers), budget level={p['budget']}, pace={p['pace']}, "
            f"interests={', '.join(p['interests']) or 'general'}, vibe={p['vibe']}, vegetarian={p['vegetarian']}, "
            f"start date={p['start']}, extra notes={p['notes'] or 'none'}")


def _num(x) -> float:
    try:
        return max(0.0, float(x))
    except (TypeError, ValueError):
        return 0.0


def norm_slot(s: dict, i: int, time: str) -> dict:
    if not isinstance(s, dict) or not s.get("title"):
        raise LLMError("AI returned an incomplete slot")
    return dict(slot=SLOTS[i], time=time, title=str(s["title"]), area=str(s.get("area") or ""),
                description=str(s.get("description") or ""), cost_local=_num(s.get("cost_local")),
                tags=[str(t) for t in (s.get("tags") or [])][:4], tip=str(s.get("tip") or TIPS[i]))


def ai_recommend(p: dict) -> list:
    month = MONTHS[p["start"].month - 1]
    prompt = (f"Recommend the 3 best-matching destinations. Traveller: {profile(p)}. Travel month: {month}, duration {p['days']} days. "
              "Weigh weather in that month, budget fit and mood. Return JSON: "
              '{"recommendations":[{"city":"","country":"","match_score":0-100,"why":["",""],"tags":["emoji + 2-3 words"],'
              '"best_months":"","est_daily_usd_pp":0,"blurb":""}]}')
    out = []
    for r in call_llm(SYS, prompt).get("recommendations", [])[:3]:
        out.append(dict(city=str(r.get("city", "?")), country=str(r.get("country", "")),
                        score=int(_num(r.get("match_score"))), why=[str(w) for w in r.get("why", [])][:3],
                        tags=[str(t) for t in r.get("tags", [])][:4], blurb=str(r.get("blurb", "")),
                        months=str(r.get("best_months", "")), daily_usd=_num(r.get("est_daily_usd_pp"))))
    if not out:
        raise LLMError("No recommendations returned")
    return out


def ai_itinerary(p: dict, dest: str) -> dict:
    n = p["days"]
    prompt = (f"Plan a {n}-day trip to {dest}. Traveller: {profile(p)}.\nRules:\n"
              f"1. Exactly {n} days; each day has exactly 4 slots in this order: {SLOTS}.\n"
              "2. GEOGRAPHIC CLUSTERING: every stop in a day must sit in ONE neighbourhood/zone (at most two adjacent zones). "
              "Order the days so the route moves progressively through the destination - never return to a zone already left.\n"
              "3. cost_local = estimated TOTAL cost for the whole party (entry, meals, local transport) in the local currency.\n"
              "4. Use real, well-known places suited to the season of the start date, the budget level and the pace.\n"
              'Return JSON: {"destination":"","country":"","currency":"ISO-4217 code","usd_per_unit_local":0,'
              '"days":[{"day":1,"theme":"","area":"main zone","slots":[' + SLOT_SCHEMA + ',...4 slots]}]}')
    raw = call_llm(SYS, prompt, 0.7)
    days = raw.get("days")
    if not isinstance(days, list) or len(days) < n:
        raise LLMError("AI returned an incomplete itinerary")
    times, out = PACE_TIMES[p["pace"]], []
    for di in range(n):
        sl = days[di].get("slots") or []
        if len(sl) < 4:
            raise LLMError("AI returned a day with missing slots")
        slots = [norm_slot(sl[i], i, times[i]) for i in range(4)]
        area = days[di].get("area") or Counter(s["area"] for s in slots).most_common(1)[0][0]
        out.append(dict(day=di + 1, date=(p["start"] + timedelta(days=di)).isoformat(),
                        theme=str(days[di].get("theme") or area), area=str(area), slots=slots))
    cur = str(raw.get("currency", "USD")).upper()[:3]
    upl = _num(raw.get("usd_per_unit_local"))
    return dict(destination=str(raw.get("destination") or dest), country=str(raw.get("country") or ""), currency=cur,
                local_per_usd=(1 / upl if upl else None), days=out, source="ai",
                generated=datetime.now().isoformat(timespec="seconds"), prefs=serial_prefs(p))


def ai_regen_day(itin: dict, di: int, request: str, keep: dict) -> dict:
    p, day = itin_prefs(itin), itin["days"][di]
    others = [s["title"] for i, d in enumerate(itin["days"]) if i != di for s in d["slots"]]
    kept = {SLOTS[i]: s["title"] for i, s in keep.items()}
    prompt = (f"Regenerate day {day['day']} of a trip to {itin['destination']}. Traveller: {profile(p)}.\n"
              f"Keep the same zone ('{day['area']}') so the route does not backtrack, unless the request says otherwise. "
              f"Do NOT reuse these places: {others}. Keep these slots exactly as they are (still return them): {kept}.\n"
              f"User request: {request or 'a fresh alternative plan'}.\n"
              f"Costs are TOTAL for the party in {itin['currency']}. Return JSON: "
              '{"theme":"","area":"","slots":[' + SLOT_SCHEMA + ',...exactly 4 slots in order: ' + str(SLOTS) + ']}')
    raw = call_llm(SYS, prompt, 0.8)
    sl = raw.get("slots") or []
    if len(sl) < 4:
        raise LLMError("AI returned incomplete day")
    slots = [keep[i] if i in keep else norm_slot(sl[i], i, PACE_TIMES[p["pace"]][i]) for i in range(4)]
    return dict(day["__class__"] if False else day, theme=str(raw.get("theme") or day["theme"]),
                area=str(raw.get("area") or day["area"]), slots=slots)


def ai_swap_slot(itin: dict, di: int, si: int, request: str) -> dict:
    p, day = itin_prefs(itin), itin["days"][di]
    used = [s["title"] for d in itin["days"] for s in d["slots"]]
    prompt = (f"In a trip to {itin['destination']} (day {day['day']}, zone '{day['area']}'), replace the "
              f"'{SLOTS[si]}' slot currently '{day['slots'][si]['title']}'. Traveller: {profile(p)}.\n"
              f"Request: {request}. Prefer the same zone (otherwise an adjacent one), avoid: {used}. "
              f"Cost is TOTAL for the party in {itin['currency']}. Return JSON for ONE slot: {SLOT_SCHEMA}")
    return norm_slot(call_llm(SYS, prompt, 0.8), si, day["slots"][si]["time"])


# ════════════════════════════════════════════════════════════════════════════
# 4. DEMO ENGINE (offline)
# ════════════════════════════════════════════════════════════════════════════
def city_pool(city: str) -> dict:
    pools = {k: [] for k in SLOT_KEYS}
    for area, slots in CITIES[city]["clusters"]:
        for k in SLOT_KEYS:
            for name, cost, tags in slots[k]:
                pools[k].append(dict(title=name, cost=cost, tags=set(tags.split()), area=area))
    return pools


def base_wanted(p: dict) -> set:
    w = set(VIBE_TAGS.get(p["vibe"], set()))
    for i in p["interests"]:
        w |= INTEREST_TAGS.get(i, set())
    return w


def parse_request(text: str):
    """'Swap museum for outdoor market' -> wanted={outdoor, market}, avoid={museum}."""
    t = text.lower()
    m = re.match(r"\s*(?:swap|replace|change)\s+(.*?)\s+(?:for|with|to)\s+(.*)", t)
    left, right = (m.group(1), m.group(2)) if m else ("", t)
    tag = lambda s: {KEYWORDS[w] for w in re.findall(r"[a-z]+", s) if w in KEYWORDS}
    wanted, avoid = tag(right), tag(left)
    return wanted - {"__cheap"}, avoid, "__cheap" in wanted


def detect_slot(text: str):
    t = text.lower()
    for words, i in ((("lunch", "brunch"), 1), (("dinner", "evening", "night"), 3), (("morning", "sunrise"), 0), (("afternoon",), 2)):
        if any(w in t for w in words):
            return i
    return None


def choose(cands, wanted, avoid, used, cheap=False, veg=False):
    def key(o):
        s = len(o["tags"] & wanted) * 2 - len(o["tags"] & avoid) * 3 + (4 if veg and "veg" in o["tags"] else 0)
        return (o["title"] in used, -s, o["cost"] if cheap else 0)
    return min(cands, key=key)


def make_slot(o: dict, i: int, p: dict) -> dict:
    cost = round(o["cost"] * BUDGET_MULT[p["budget"]] * p["travellers"])
    desc = ". ".join(TAG_DESC[t] for t in sorted(o["tags"]) if t in TAG_DESC)[:2]
    return dict(slot=SLOTS[i], time=PACE_TIMES[p["pace"]][i], title=o["title"], area=o["area"],
                description=(desc + ".") if desc else "", cost_local=float(cost), tags=sorted(o["tags"]), tip=TIPS[i])


def build_day_demo(city, area, day_no, date_iso, p, used, wanted_x=frozenset(), avoid_x=frozenset(), cheap=False, keep=None):
    pools, keep = city_pool(city), keep or {}
    base = base_wanted(p) | set(wanted_x)
    avoid = set(avoid_x) | ({"nightlife"} if p["party"] == "Family" else set())
    slots = []
    for i, k in enumerate(SLOT_KEYS):
        if i in keep:
            slots.append(keep[i])
            continue
        cands = [o for o in pools[k] if o["area"] == area]
        if p["vegetarian"] and i == 1:
            cands = [o for o in cands if "veg" in o["tags"]] or cands
        w = base | (PACE_TAGS.get(p["pace"], set()) if i == 2 else set())
        o = choose(cands, w, avoid, used, cheap, p["vegetarian"])
        used.add(o["title"])
        slots.append(make_slot(o, i, p))
    return dict(day=day_no, date=date_iso, theme=area, area=area, slots=slots)


def demo_itinerary(p: dict, city: str) -> dict:
    c, n = CITIES[city], p["days"]
    areas = [a for a, _ in c["clusters"]]
    w, pools = base_wanted(p), city_pool(city)
    score = {a: sum(len(o["tags"] & w) for k in SLOT_KEYS for o in pools[k] if o["area"] == a) for a in areas}
    k = min(n, len(areas))
    chosen = sorted(sorted(areas, key=lambda a: -score[a])[:k], key=areas.index)  # keep geographic route order
    used, days = set(), []
    for i in range(n):  # consecutive days stay in one zone -> no backtracking
        area = chosen[min(k - 1, i * k // n)]
        days.append(build_day_demo(city, area, i + 1, (p["start"] + timedelta(days=i)).isoformat(), p, used))
    return dict(destination=city, country=c["country"], currency=c["cur"], local_per_usd=FX.get(c["cur"]), days=days,
                source="demo", generated=datetime.now().isoformat(timespec="seconds"), prefs=serial_prefs(p))


def demo_swap(itin, di, si, request):
    city = match_city(itin["destination"])
    if not city:
        raise LLMError("Demo engine only covers: " + ", ".join(CITIES) + ". Enable AI mode for other destinations.")
    wanted, avoid, cheap = parse_request(request)
    day = itin["days"][di]
    cur = day["slots"][si]["title"]
    used = {s["title"] for d in itin["days"] for s in d["slots"]}
    cands = [o for o in city_pool(city)[SLOT_KEYS[si]] if o["title"] != cur]
    same = [o for o in cands if o["area"] == day["area"]]
    sc = lambda o: len(o["tags"] & wanted) * 2 - len(o["tags"] & avoid) * 3
    pool = same if same and max(sc(o) for o in same) > 0 else cands  # stay in-zone whenever possible
    if not (wanted or avoid or cheap):
        pool = same or cands
    best = choose(pool, wanted, avoid, used, cheap, "veg" in wanted)
    return make_slot(best, si, itin_prefs(itin))


def demo_regen_day(itin, di, wanted, avoid, cheap, keep):
    city = match_city(itin["destination"])
    if not city:
        raise LLMError("Demo engine only covers: " + ", ".join(CITIES))
    day = itin["days"][di]
    used = {s["title"] for i, d in enumerate(itin["days"]) if i != di for s in d["slots"]}
    used |= {s["title"] for i, s in enumerate(day["slots"]) if i not in keep}  # force fresh picks
    new = build_day_demo(city, day["area"], day["day"], day["date"], itin_prefs(itin), used, wanted, avoid, cheap, keep)
    return new


def est_daily_usd(city: str, budget: str) -> float:
    c, pools = CITIES[city], city_pool(city)
    local = sum(sum(o["cost"] for o in pools[k]) / len(pools[k]) for k in SLOT_KEYS) * BUDGET_MULT[budget]
    usd, _ = conv(dict(currency=c["cur"]), local)
    return usd or 0.0


def recommend_demo(p: dict) -> list:
    month, target = p["start"].month, {"Budget": 1, "Moderate": 2, "Luxury": 3}[p["budget"]]
    out = []
    for name, c in CITIES.items():
        s, why = 0, []
        if p["vibe"] in c["vibes"]:
            s += 35
            why.append(f"Fits your {p['vibe'].lower()} mood")
        if month in c["months"]:
            s += 30
            why.append(f"{MONTHS[month - 1]} is in peak season")
        elif ((month % 12) + 1) in c["months"] or (((month - 2) % 12) + 1) in c["months"]:
            s += 12
            why.append(f"{MONTHS[month - 1]} is shoulder season (fewer crowds)")
        gap = abs(c["tier"] - target)
        s += (20, 10, 0)[gap]
        if gap == 0:
            why.append(f"Matches your {p['budget'].lower()} budget")
        hit = c["fit"] & set(p["interests"])
        s += min(15, 5 * len(hit))
        if hit:
            why.append("Great for " + ", ".join(sorted(h.lower() for h in hit)))
        mm = [m for m in range(1, 13) if m in c["months"]]
        out.append(dict(city=name, country=c["country"], score=min(99, s), why=why, tags=c["tags"], blurb=c["blurb"],
                        months=", ".join(MONTHS[m - 1] for m in mm) if len(mm) < 8 else "Most of the year",
                        daily_usd=est_daily_usd(name, p["budget"])))
    return sorted(out, key=lambda r: -r["score"])[:3]


# ════════════════════════════════════════════════════════════════════════════
# 5. PERSISTENCE (simulated database)
# ════════════════════════════════════════════════════════════════════════════
DB_DIR = Path("data")


class TripStore:
    """Session-backed store mirrored best-effort to data/trips_<workspace>.json (ephemeral on Community Cloud)."""

    def __init__(self, workspace: str):
        self.ws = re.sub(r"[^A-Za-z0-9_-]", "", workspace)[:24] or "default"
        self.path = DB_DIR / f"trips_{self.ws}.json"

    def all(self) -> list:
        mem = ss.setdefault("_db", {})
        if self.ws not in mem:
            try:
                mem[self.ws] = json.loads(self.path.read_text("utf-8")) if self.path.exists() else []
            except Exception:
                mem[self.ws] = []
        return mem[self.ws]

    def _flush(self):
        try:
            DB_DIR.mkdir(exist_ok=True)
            self.path.write_text(json.dumps(self.all(), ensure_ascii=False, indent=1), "utf-8")
        except Exception:
            pass  # read-only filesystem: stay session-only

    def save(self, rec: dict):
        trips = self.all()
        for i, t in enumerate(trips):
            if t["id"] == rec["id"]:
                trips[i] = rec
                break
        else:
            trips.append(rec)
        self._flush()

    def delete(self, tid: str):
        ss["_db"][self.ws] = [t for t in self.all() if t["id"] != tid]
        self._flush()


def store() -> TripStore:
    return TripStore(ss.workspace)


def load_trip_cb(rec: dict):
    it = copy.deepcopy(rec["itinerary"])
    p = itin_prefs(it)
    ss.update(f_dest=it["destination"], f_vibe=p["vibe"], f_days=p["days"], f_start=p["start"], f_budget=p["budget"],
              f_party=p["party"], f_trav=p["travellers"], f_pace=p["pace"], f_interests=p["interests"],
              f_veg=p["vegetarian"], f_notes=p.get("notes", ""), itin=it, active_trip=rec["id"], undo=[], log=[])


def use_city_cb(city: str):
    ss.f_dest = city
    ss.picked = city


# ════════════════════════════════════════════════════════════════════════════
# 6. PDF EXPORT
# ════════════════════════════════════════════════════════════════════════════
def _t(s) -> str:
    """Make text safe for built-in PDF fonts (latin-1)."""
    s = str(s if s is not None else "")
    for a, b in (("–", "-"), ("—", "-"), ("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("•", "-"), ("→", "->"),
                 ("₹", "INR "), ("…", "..."), ("œ", "oe"), ("Œ", "Oe")):
        s = s.replace(a, b)
    return s.encode("latin-1", "ignore").decode("latin-1")


def build_pdf(itin: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape as xesc

    TEAL, SUN, INK, MUTED, SAND = (colors.HexColor(h) for h in ("#0f766e", "#f59e0b", "#1f2937", "#6b7280", "#fff7ed"))
    W, H = A4
    p = itin_prefs(itin)
    cur = itin["currency"]

    def S(name, **kw):
        return ParagraphStyle(name, fontName=kw.pop("font", "Helvetica"), textColor=kw.pop("color", INK), **kw)
    sty = dict(body=S("b", fontSize=9, leading=12), bold=S("bd", font="Helvetica-Bold", fontSize=10, leading=13),
               small=S("s", fontSize=8, leading=10.5, color=MUTED), tip=S("t", font="Helvetica-Oblique", fontSize=8, leading=10.5, color=TEAL),
               h1=S("h1", font="Helvetica-Bold", fontSize=15, leading=19, color=colors.white),
               h2=S("h2", font="Helvetica-Bold", fontSize=13, leading=17, color=TEAL), time=S("tm", font="Helvetica-Bold", fontSize=10, color=TEAL),
               cost=S("c", font="Helvetica-Bold", fontSize=9, leading=12, alignment=2))

    def P(text, style="body"):
        return Paragraph(xesc(_t(text)), sty[style])

    def money(amt):
        usd, inr = conv(itin, amt)
        return f"{cur} {amt:,.0f}" + ("" if usd is None else f"<br/>USD {usd:,.0f} / INR {inr:,.0f}")

    def PM(amt, style="cost"):
        return Paragraph(_t(money(amt)).replace("<br/>", "<br/>"), sty[style])

    def chrome(c, doc):
        c.saveState()
        if doc.page == 1:
            c.setFillColor(TEAL); c.rect(0, H - 92 * mm, W, 92 * mm, fill=1, stroke=0)
            c.setFillColor(SUN); c.rect(0, H - 97 * mm, W, 5 * mm, fill=1, stroke=0)
            c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 30)
            c.drawString(18 * mm, H - 42 * mm, _t(f"{itin['destination']}"))
            c.setFont("Helvetica", 14)
            c.drawString(18 * mm, H - 54 * mm, _t(f"{p['days']}-day personalised itinerary  |  {itin.get('country', '')}"))
            c.setFont("Helvetica-Oblique", 11)
            end = p["start"] + timedelta(days=p["days"] - 1)
            c.drawString(18 * mm, H - 66 * mm, f"{p['start']:%d %b %Y} - {end:%d %b %Y}")
            c.setFont("Helvetica", 9)
            c.drawString(18 * mm, H - 82 * mm, "Offline travel guide  |  Generated by Wanderlust Itinerary Planner")
        c.setFont("Helvetica", 8); c.setFillColor(MUTED)
        c.drawCentredString(W / 2, 9 * mm, _t(f"{itin['destination']} itinerary  |  page {doc.page}"))
        c.restoreState()

    def band(text, color=TEAL):
        t = Table([[Paragraph(_t(text), sty["h1"])]], colWidths=[W - 36 * mm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), color), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        return t

    total = itin_total(itin)
    story = [Spacer(1, 88 * mm), P("Trip at a glance", "h2"), Spacer(1, 3 * mm)]
    glance = [("Destination", f"{itin['destination']}, {itin.get('country', '')}"), ("Travellers", f"{p['travellers']} ({p['party']})"),
              ("Budget level", p["budget"]), ("Pace", p["pace"]), ("Interests", ", ".join(p["interests"]) or "General"),
              ("Vegetarian", "Yes" if p["vegetarian"] else "No"), ("Estimated total", _t(money(total)).replace("<br/>", "  /  "))]
    g = Table([[P(a, "bold"), P(b)] for a, b in glance], colWidths=[40 * mm, 130 * mm])
    g.setStyle(TableStyle([("ROWBACKGROUNDS", (0, 0), (-1, -1), [SAND, colors.white]), ("TOPPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [g, Spacer(1, 6 * mm), P("Day overview", "h2"), Spacer(1, 2 * mm)]
    ov = Table([[P(f"Day {d['day']}", "bold"), P(fmt_date(d["date"])), P(d["theme"]), P(d["area"], "small")] for d in itin["days"]],
               colWidths=[18 * mm, 42 * mm, 60 * mm, 50 * mm])
    ov.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [ov, PageBreak()]

    cum = 0.0
    for d in itin["days"]:
        dt = day_total(d)
        cum += dt
        story += [band(f"Day {d['day']}  |  {fmt_date(d['date'])}  |  {d['theme']}"), Spacer(1, 2 * mm),
                  P(f"Zone: {d['area']}  -  stops are clustered to minimise transit time.", "small"), Spacer(1, 2 * mm)]
        rows = []
        for s in d["slots"]:
            det = [P(s["slot"], "small"), P(s["title"], "bold"), P(f"{s['area']}", "small")]
            if s["description"]:
                det.append(P(s["description"]))
            det.append(P("Tip: " + s["tip"], "tip"))
            rows.append([P(s["time"], "time"), det, PM(s["cost_local"])])
        t = Table(rows, colWidths=[20 * mm, 112 * mm, 38 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        tot = Table([[P("Day total", "bold"), PM(dt), P("Running total", "bold"), PM(cum)]], colWidths=[25 * mm, 55 * mm, 30 * mm, 60 * mm])
        tot.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SAND), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story += [t, Spacer(1, 3 * mm), tot, PageBreak()]

    story += [band("Budget summary", SUN), Spacer(1, 3 * mm)]
    hdr = [P(h, "bold") for h in ("Day", "Date", "Day cost", "Cumulative")]
    cum, brow = 0.0, [hdr]
    for d in itin["days"]:
        cum += day_total(d)
        brow.append([P(str(d["day"])), P(f"{date.fromisoformat(d['date']):%d %b}"), PM(day_total(d), "body"), PM(cum, "body")])
    brow.append([P("Total", "bold"), "", PM(total, "body"), ""])
    bt = Table(brow, colWidths=[18 * mm, 30 * mm, 60 * mm, 62 * mm], repeatRows=1)
    bt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), SAND), ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                            ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [bt, Spacer(1, 3 * mm), P("Costs are planning estimates for the whole party, excluding accommodation and international flights. "
                                       f"Exchange rate used: 1 USD = {ss.usd_inr:.2f} INR.", "small"), PageBreak()]

    story += [band("Emergency contacts & safety checklist", colors.HexColor("#be123c")), Spacer(1, 3 * mm), P("Local emergency numbers", "h2")]
    nums = EMERGENCY.get(itin.get("country", ""), [("Universal emergency (many countries)", "112"), ("Local numbers", "Confirm on arrival")])
    nt = Table([[P(a), P(b, "bold")] for a, b in nums], colWidths=[110 * mm, 60 * mm])
    nt.setStyle(TableStyle([("ROWBACKGROUNDS", (0, 0), (-1, -1), [SAND, colors.white])]))
    story += [nt, P("Verify numbers before travelling.", "small"), Spacer(1, 4 * mm)]
    lists = {"Before you go": ["Passport valid 6+ months", "Visa / e-visa approved", "Travel insurance bought", "Copies of passport & tickets (offline + paper)",
                               "Bank notified; some local currency", "eSIM / local SIM & offline maps", "Medicines & vaccinations sorted"],
             "Fill in": ["Embassy / consulate phone: ____________________", "Hotel name, address & phone: ____________________",
                         "Insurance 24h helpline & policy no.: ____________________", "Emergency contact at home: ____________________",
                         "Blood group / allergies: ____________________"],
             "On the road": ["Share this itinerary with a trusted person", "Keep cash and cards in separate places", "Save hospital & police station locations offline",
                             "Use licensed taxis / ride apps", "Drink safe water; carry basic first-aid"]}
    for title, items in lists.items():
        story += [P(title, "h2")] + [P("[   ]  " + i) for i in items] + [Spacer(1, 3 * mm)]

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                      title=_t(f"{itin['destination']} itinerary"), author="Wanderlust Itinerary Planner").build(story, onFirstPage=chrome, onLaterPages=chrome)
    return buf.getvalue()


@st.cache_data(show_spinner=False)
def pdf_bytes(itin_json: str, usd_inr: float) -> bytes:
    return build_pdf(json.loads(itin_json))


# ════════════════════════════════════════════════════════════════════════════
# 7. UI
# ════════════════════════════════════════════════════════════════════════════
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:wght@600;800&family=Inter:wght@400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.hero { background: linear-gradient(120deg,#0f766e 0%,#14b8a6 38%,#f59e0b 78%,#fb7185 100%); border-radius: 20px;
        padding: 30px 34px; color: #fff; margin-bottom: 18px; box-shadow: 0 10px 30px rgba(15,118,110,.25); }
.hero h1 { font-family: 'Fraunces', serif; font-weight: 800; font-size: 2.3rem; margin: 0; color: #fff; }
.hero p { margin: 6px 0 0; font-size: 1.05rem; opacity: .95; }
.card { background: #fff; color: #1f2937; border-radius: 16px; padding: 18px 20px; box-shadow: 0 4px 18px rgba(0,0,0,.08);
        border-top: 5px solid #14b8a6; height: 100%; }
.card h3 { font-family: 'Fraunces', serif; margin: 0 0 2px; color: #0f766e; }
.rank { float: right; background: #f59e0b; color: #fff; font-weight: 700; border-radius: 999px; padding: 2px 12px; }
.chip { display: inline-block; background: #ecfeff; color: #0f766e; border: 1px solid #99f6e4; border-radius: 999px;
        padding: 2px 10px; margin: 2px 4px 2px 0; font-size: .78rem; font-weight: 500; }
.chip.warm { background: #fff7ed; color: #b45309; border-color: #fed7aa; }
.chip.bad { background: #fff1f2; color: #be123c; border-color: #fecdd3; }
.slot { display: flex; gap: 14px; background: #fff; color: #1f2937; border-radius: 14px; padding: 14px 16px; margin: 10px 0;
        box-shadow: 0 2px 10px rgba(0,0,0,.07); border-left: 6px solid #14b8a6; }
.slot.s1 { border-left-color: #f59e0b; } .slot.s2 { border-left-color: #38bdf8; } .slot.s3 { border-left-color: #fb7185; }
.slot-time { min-width: 86px; font-weight: 700; color: #0f766e; } .slot-body { flex: 1; }
.slot-name { font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; color: #6b7280; }
.slot-title { font-weight: 600; font-size: 1.05rem; } .slot-meta { color: #6b7280; font-size: .85rem; margin: 2px 0; }
.slot-desc { font-size: .9rem; } .slot-tip { font-size: .8rem; color: #0f766e; margin-top: 4px; }
.slot-cost { text-align: right; font-weight: 700; min-width: 120px; color: #b45309; } .slot-cost small { color: #6b7280; font-weight: 500; }
.runbar { background: linear-gradient(90deg,#fff7ed,#ecfeff); color: #1f2937; border-radius: 12px; padding: 10px 14px; font-weight: 600; margin-top: 6px; }
div.stButton > button[kind="primary"], div.stDownloadButton > button[kind="primary"] { background: linear-gradient(90deg,#0f766e,#f59e0b); border: 0; color: #fff; font-weight: 600; }
</style>
"""


def chips(items, cls=""):
    return "".join(f'<span class="chip {cls}">{esc(i)}</span>' for i in items)


def slot_card(itin: dict, s: dict, i: int) -> str:
    usd, inr = conv(itin, s["cost_local"])
    sub = "" if usd is None else f"<br><small>${usd:,.0f} · ₹{inr:,.0f}</small>"
    return ("".join([
        f'<div class="slot s{i}"><div class="slot-time">{SLOT_ICON[i]} {esc(s["time"])}</div><div class="slot-body">',
        f'<div class="slot-name">{esc(s["slot"])}</div><div class="slot-title">{esc(s["title"])}</div>',
        f'<div class="slot-meta">📍 {esc(s["area"])}</div>', chips(s.get("tags", [])),
        f'<div class="slot-desc">{esc(s["description"])}</div><div class="slot-tip">💡 {esc(s["tip"])}</div></div>',
        f'<div class="slot-cost">{esc(itin["currency"])} {s["cost_local"]:,.0f}{sub}</div></div>']))


def zone_badge(day: dict) -> str:
    areas = list(dict.fromkeys(s["area"] for s in day["slots"] if s["area"]))
    if len(areas) <= 1:
        return chips([f"✅ Single zone: {day['area']} - zero backtracking"])
    if len(areas) == 2:
        return chips([f"🟡 2 adjacent zones: {' + '.join(areas)}"], "warm")
    return chips([f"🔴 {len(areas)} zones - consider swapping for a closer stop"], "bad")


def sidebar():
    with st.sidebar:
        st.markdown("## 🧭 Wanderlust Studio")
        st.toggle("Demo mode (no API key needed)", key="demo", help="Uses the built-in offline engine with 6 curated destinations.")
        st.radio("AI provider", ["Gemini", "Groq"], key="provider", horizontal=True, disabled=ss.demo)
        st.text_input("API key", type="password", key="api_key", disabled=ss.demo, placeholder="Paste key (kept in this session only)",
                      help="Never stored on disk or logged. On Streamlit Cloud you can set GEMINI_API_KEY / GROQ_API_KEY in Secrets instead.")
        with st.expander("Advanced"):
            st.text_input("Gemini model", key="m_gemini")
            st.text_input("Groq model", key="m_groq")
        st.number_input("USD → INR rate", 50.0, 150.0, step=0.5, key="usd_inr", help="Used for all INR conversions.")
        st.text_input("Workspace code", key="workspace", help="Trips are saved under this code. Re-enter it later to reopen them.")
        if ss.demo:
            st.info("🟡 Demo mode: offline engine active.")
        elif current_key():
            st.success(f"🟢 Live AI via {ss.provider}")
        else:
            st.warning("No API key found - falling back to demo engine.")
        st.caption("Estimates only. Always verify prices, opening hours and entry rules before travelling.")


def prefs_form():
    with st.expander("🎒 Trip preferences", expanded=ss.itin is None):
        with st.form("prefs"):
            c1, c2, c3 = st.columns(3)
            c1.text_input("Destination (leave blank to get recommendations)", key="f_dest", placeholder="e.g. Jaipur, Paris, Kyoto...")
            c1.selectbox("Open-ended vibe", VIBES, key="f_vibe")
            c1.number_input("Duration (days)", 1, 14, key="f_days")
            c2.date_input("Travel start date", key="f_start", min_value=date.today())
            c2.selectbox("Budget level", ["Budget", "Moderate", "Luxury"], key="f_budget")
            c2.selectbox("Pace", ["Relaxed", "Moderate", "Fast-Paced"], key="f_pace")
            c3.selectbox("Travel party", ["Solo", "Couple", "Family", "Friends"], key="f_party")
            c3.number_input("Number of travellers", 1, 20, key="f_trav")
            c3.checkbox("Vegetarian meals", key="f_veg")
            st.multiselect("Interests", INTERESTS, key="f_interests")
            st.text_input("Anything else? (optional)", key="f_notes", placeholder="e.g. travelling with grandparents, love street photography")
            if st.form_submit_button("💾 Apply preferences", type="primary"):
                st.toast("Preferences applied")
        p = get_prefs()
        end = p["start"] + timedelta(days=p["days"] - 1)
        st.caption(f"📅 {p['start']:%d %b} → {end:%d %b %Y}  ·  {p['days']} days  ·  {p['travellers']} traveller(s)")


# ── Tab 1 ────────────────────────────────────────────────────────────────────
def tab_recommender():
    st.subheader("Smart Destination Recommender")
    st.caption("No fixed destination? We rank cities on your mood, travel-month weather, budget and interests.")
    if st.button("🔍 Find my top 3 destinations", type="primary"):
        p = get_prefs()
        with st.spinner("Matching destinations..."):
            recs = None
            if ai_enabled():
                try:
                    recs = ai_recommend(p)
                except LLMError as e:
                    st.warning(f"AI unavailable ({e}). Showing demo recommendations.")
            ss.recs = recs or recommend_demo(p)
    if ss.picked:
        st.success(f"✅ **{ss.picked}** selected. Open the *Day-by-Day Itinerary* tab to generate your plan.")
    for col, (i, r) in zip(st.columns(3), enumerate(ss.recs or [])):
        with col:
            why = "".join(f"<li>{esc(w)}</li>" for w in r["why"])
            daily = f"~${r['daily_usd']:,.0f} (₹{r['daily_usd'] * ss.usd_inr:,.0f})" if r["daily_usd"] else "n/a"
            st.markdown(f'<div class="card"><span class="rank">#{i + 1} · {r["score"]}% match</span><h3>{esc(r["city"])}</h3>'
                        f'<div style="color:#6b7280">{esc(r["country"])}</div><p>{esc(r["blurb"])}</p>{chips(r["tags"])}'
                        f'<ul style="padding-left:18px;font-size:.88rem">{why}</ul>'
                        f'<div style="font-size:.85rem">🗓️ <b>Best months:</b> {esc(r["months"])}<br>💸 <b>Food + activities / person / day:</b> {daily}</div></div>',
                        unsafe_allow_html=True)
            st.button(f"Plan {r['city']} →", key=f"use_{i}", on_click=use_city_cb, args=(r["city"],), use_container_width=True)


# ── Tab 2 ────────────────────────────────────────────────────────────────────
def generate_itinerary():
    p = get_prefs()
    dest = p["destination"] or (ss.recs[0]["city"] if ss.recs else "")
    if not dest:
        st.warning("Enter a destination in the preferences, or run the recommender first.")
        return
    itin = None
    with st.spinner(f"Building a geographically-clustered plan for {dest}..."):
        if ai_enabled():
            try:
                itin = ai_itinerary(p, dest)
            except LLMError as e:
                st.warning(f"AI unavailable ({e}). Switched to the demo engine.")
        if itin is None:
            city = match_city(dest)
            if not city:
                city = recommend_demo(p)[0]["city"]
                st.warning(f"Demo mode covers {', '.join(CITIES)}. Using **{city}** (best match for your vibe). Enable AI mode for any destination.")
            itin = demo_itinerary(p, city)
    ss.itin, ss.undo, ss.log, ss.active_trip = itin, [], [], None


def cost_df(itin: dict) -> pd.DataFrame:
    rows, cum = [], 0.0
    for d in itin["days"]:
        for i, s in enumerate(d["slots"]):
            c = float(s["cost_local"])
            cum += c
            (u, n), (cu, cn) = conv(itin, c), conv(itin, cum)
            rows.append({"Day": d["day"], "Slot": SLOT_SHORT[i], "Activity": s["title"], f"Cost ({itin['currency']})": c,
                         "USD": u, "INR": n, f"Cumulative ({itin['currency']})": cum, "Cumulative USD": cu, "Cumulative INR": cn})
    return pd.DataFrame(rows)


def render_tracker(itin: dict):
    p = itin_prefs(itin)
    total = itin_total(itin)
    usd, inr = conv(itin, total)
    ref = DAILY_REF_USD[p["budget"]] * p["days"] * p["travellers"]
    st.markdown("#### 💰 Itemised costs & running budget")
    m = st.columns(4)
    m[0].metric(f"Total ({itin['currency']})", f"{total:,.0f}")
    m[1].metric("Total USD", "n/a" if usd is None else f"${usd:,.0f}")
    m[2].metric("Total INR", "n/a" if inr is None else f"₹{inr:,.0f}")
    if usd is not None:
        m[3].metric(f"vs {p['budget']} guide", f"${ref:,.0f}", f"{usd - ref:+,.0f} USD", delta_color="inverse")
        st.progress(min(1.0, usd / ref), text=f"{usd / ref:.0%} of the {p['budget'].lower()} food + activities guide (${ref:,.0f})")
    df = cost_df(itin)
    st.dataframe(df, hide_index=True, use_container_width=True)
    c1, c2 = st.columns(2)
    key = "Cumulative USD" if usd is not None else f"Cumulative ({itin['currency']})"
    c1.caption("Cumulative spend")
    c1.line_chart(df.set_index(pd.Index(range(1, len(df) + 1), name="Stop #"))[key])
    daily = df.groupby("Day")[f"Cost ({itin['currency']})"].sum()
    c2.caption(f"Cost per day ({itin['currency']})")
    c2.bar_chart(daily)


def tab_itinerary():
    st.subheader("Day-by-Day Optimised Itinerary")
    if st.button("✨ Generate itinerary", type="primary"):
        generate_itinerary()
    itin = ss.itin
    if not itin:
        st.info("Set your preferences, then click **Generate itinerary**.")
        return
    bt = backtracking(itin)
    route = " → ".join(dict.fromkeys(d["area"] for d in itin["days"]))
    st.markdown(f"### {esc(itin['destination'])}, {esc(itin.get('country', ''))}", unsafe_allow_html=True)
    st.markdown(chips([f"🧭 Route: {route}"]) + chips(["✅ No backtracking across zones"] if bt == 0 else [f"⚠️ {bt} zone revisit(s)"], "" if bt == 0 else "bad")
                + chips(["AI-generated" if itin.get("source") == "ai" else "Demo engine"], "warm"), unsafe_allow_html=True)
    cum = 0.0
    for d in itin["days"]:
        cum += day_total(d)
        with st.expander(f"Day {d['day']} · {fmt_date(d['date'])} · {d['theme']}  -  {itin['currency']} {day_total(d):,.0f}", expanded=d["day"] == 1):
            st.markdown(zone_badge(d), unsafe_allow_html=True)
            st.markdown("".join(slot_card(itin, s, i) for i, s in enumerate(d["slots"])), unsafe_allow_html=True)
            st.markdown(f'<div class="runbar">Day total: {esc(trio(itin, day_total(d)))}<br>Running total after day {d["day"]}: {esc(trio(itin, cum))}</div>',
                        unsafe_allow_html=True)
    render_tracker(itin)


# ── Tab 3 ────────────────────────────────────────────────────────────────────
def run_swap(di: int, si: int, request: str):
    itin = ss.itin
    new = None
    try:
        if ai_enabled():
            try:
                new = ai_swap_slot(itin, di, si, request)
            except LLMError as e:
                st.warning(f"AI unavailable ({e}). Using demo engine.")
        if new is None:
            new = demo_swap(itin, di, si, request)
    except LLMError as e:
        st.error(str(e))
        return
    push_undo(f"Day {di + 1} {SLOT_SHORT[si]}: {itin['days'][di]['slots'][si]['title']} → {new['title']}")
    itin["days"][di]["slots"][si] = new
    if new["area"] != itin["days"][di]["area"]:
        st.warning(f"No in-zone match found, so this stop is in **{new['area']}** (adjacent to {itin['days'][di]['area']}). Expect a short transfer.")
    st.rerun()


def run_regen(di: int, vibes: list, text: str, keep_idx: list):
    itin = ss.itin
    wanted, avoid, cheap = parse_request(text)
    for v in vibes:
        w, a = DAY_VIBES[v]
        wanted |= w - {"__cheap"}
        avoid |= a
        cheap |= "__cheap" in w
    keep = {i: itin["days"][di]["slots"][i] for i in keep_idx}
    req = ", ".join(vibes + ([text] if text else []))
    new = None
    try:
        if ai_enabled():
            try:
                new = ai_regen_day(itin, di, req, keep)
            except LLMError as e:
                st.warning(f"AI unavailable ({e}). Using demo engine.")
        if new is None:
            new = demo_regen_day(itin, di, wanted, avoid, cheap, keep)
    except LLMError as e:
        st.error(str(e))
        return
    push_undo(f"Regenerated day {di + 1} ({req or 'fresh take'})")
    itin["days"][di] = new
    st.rerun()


def tab_swap():
    st.subheader("Vibe Customisation & Dynamic Activity Swap")
    itin = ss.itin
    if not itin:
        st.info("Generate an itinerary first (Tab 2).")
        return
    di = st.selectbox("Day", range(len(itin["days"])), format_func=lambda i: f"Day {i + 1} - {itin['days'][i]['theme']}")
    day = itin["days"][di]
    st.markdown("".join(slot_card(itin, s, i) for i, s in enumerate(day["slots"])), unsafe_allow_html=True)

    st.markdown("##### 🔄 Swap one activity")
    c1, c2 = st.columns([1, 2])
    si = c1.selectbox("Slot", range(4), format_func=lambda i: SLOTS[i])
    quick = c2.selectbox("Quick request", QUICK)
    custom = st.text_input("Or describe what you want", placeholder="e.g. Swap museum for outdoor market / Find vegetarian lunch spot")
    request = custom.strip() or ("" if quick == QUICK[-1] else quick)
    hint = detect_slot(request)
    if hint is not None and hint != si:
        st.caption(f"ℹ️ Your request mentions {SLOT_SHORT[hint].lower()} - swapping the **{SLOTS[hint]}** slot.")
        si = hint
    if st.button("🔄 Swap this activity", type="primary", disabled=not request):
        run_swap(di, si, request)

    st.divider()
    st.markdown("##### ♻️ Regenerate this whole day (other days stay untouched)")
    vibes = st.multiselect("Day vibe", list(DAY_VIBES))
    text = st.text_input("Extra instructions (optional)", key="regen_text", placeholder="e.g. more street food, avoid long walks")
    keep = st.multiselect("🔒 Keep these slots", range(4), format_func=lambda i: SLOTS[i])
    c1, c2 = st.columns(2)
    if c1.button(f"♻️ Regenerate Day {di + 1}", type="primary"):
        run_regen(di, vibes, text.strip(), keep)
    if c2.button("↩️ Undo last change", disabled=not ss.undo):
        ss.itin = ss.undo.pop()
        ss.log.insert(0, f"{datetime.now():%H:%M} - Undo")
        st.rerun()
    if ss.log:
        with st.expander("Change log"):
            st.write("\n".join(f"- {x}" for x in ss.log[:15]))


# ── Tab 4 ────────────────────────────────────────────────────────────────────
def tab_trips():
    st.subheader("Trip Management & Offline PDF Export")
    db, itin = store(), ss.itin
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### 💾 Save to trip history")
        if itin:
            name = st.text_input("Trip name", value=f"{itin['destination']} · {len(itin['days'])} days", key="trip_name")
            b1, b2 = st.columns(2)
            if ss.active_trip and b1.button("Update saved trip", type="primary"):
                db.save(dict(id=ss.active_trip, name=name, saved_at=datetime.now().isoformat(timespec="seconds"), itinerary=copy.deepcopy(itin)))
                st.success("Trip updated.")
            if b2.button("Save as new trip", type="primary" if not ss.active_trip else "secondary"):
                tid = uuid.uuid4().hex[:8]
                db.save(dict(id=tid, name=name, saved_at=datetime.now().isoformat(timespec="seconds"), itinerary=copy.deepcopy(itin)))
                ss.active_trip = tid
                st.success(f"Saved under workspace “{db.ws}”.")
        else:
            st.info("Generate an itinerary to save it.")
    with c2:
        st.markdown("##### 📄 Offline PDF travel guide")
        if itin:
            try:
                data = pdf_bytes(json.dumps(itin, sort_keys=True), float(ss.usd_inr))
                st.download_button("⬇️ Export PDF itinerary", data, file_name=f"{re.sub(r'[^A-Za-z0-9]+', '_', itin['destination'])}_itinerary.pdf",
                                   mime="application/pdf", type="primary", use_container_width=True)
                st.caption("Includes day plans, costs in local/USD/INR, budget summary and an emergency checklist.")
            except Exception as e:  # noqa: BLE001 - surface any rendering problem without crashing the app
                st.error(f"Could not build the PDF: {e}")
        else:
            st.info("Nothing to export yet.")

    st.divider()
    st.markdown(f"##### 🗂️ Trip history · workspace `{db.ws}`")
    trips = db.all()
    if not trips:
        st.caption("No saved trips yet.")
    else:
        rows = []
        for t in trips:
            it = t["itinerary"]
            u, _ = conv(it, itin_total(it))
            rows.append({"Name": t["name"], "Destination": it["destination"], "Days": len(it["days"]), "Starts": it["days"][0]["date"],
                         "Est. total (USD)": None if u is None else round(u), "Saved": t["saved_at"].replace("T", " ")})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        sel = st.selectbox("Open a trip", trips, format_func=lambda t: f"{t['name']}  ({t['saved_at'][:10]})")
        b1, b2, b3 = st.columns(3)
        b1.button("📂 Load trip", on_click=load_trip_cb, args=(sel,), use_container_width=True)
        b2.download_button("⬇️ Trip JSON", json.dumps(sel, indent=1), file_name=f"trip_{sel['id']}.json", mime="application/json", use_container_width=True)
        if b3.button("🗑️ Delete", use_container_width=True):
            db.delete(sel["id"])
            st.rerun()
    up = st.file_uploader("Import a trip JSON", type="json")
    if up is not None and ss.last_import != (up.name, up.size):
        try:
            rec = json.loads(up.getvalue().decode("utf-8"))
            assert {"itinerary", "name"} <= rec.keys() and rec["itinerary"]["days"]
            rec["id"] = uuid.uuid4().hex[:8]
            db.save(rec)
            ss.last_import = (up.name, up.size)
            st.rerun()
        except Exception:  # noqa: BLE001
            st.error("That file is not a valid trip export.")
    st.caption("ℹ️ Storage is simulated: session memory mirrored to a local JSON file. On Streamlit Community Cloud the file resets on reboot - download the JSON to keep a permanent copy.")


def main():
    init_state()
    st.markdown(CSS, unsafe_allow_html=True)
    sidebar()
    st.markdown('<div class="hero"><h1>🧭 Personalized Travel Itinerary Planner</h1>'
                '<p>Pick a vibe, get clustered day plans, swap anything on the fly, and carry it all offline.</p></div>', unsafe_allow_html=True)
    prefs_form()
    t1, t2, t3, t4 = st.tabs(["🧭 Destination Recommender", "🗓️ Day-by-Day Itinerary", "🎛️ Vibe & Swap Studio", "🧳 Trips & PDF Export"])
    for tab, fn in zip((t1, t2, t3, t4), (tab_recommender, tab_itinerary, tab_swap, tab_trips)):
        with tab:
            try:
                fn()
            except Exception as e:  # noqa: BLE001 - keep other tabs alive if one fails
                st.error(f"Something went wrong in this tab: {e}")


if __name__ == "__main__":
    main()
