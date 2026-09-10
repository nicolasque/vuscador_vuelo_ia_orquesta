"""Configuration module for Vusca Vuelos Orquesta."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# AI Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

# Flight APIs Configuration
AMADEUS_CLIENT_ID = os.getenv("AMADEUS_CLIENT_ID", "").strip()
AMADEUS_CLIENT_SECRET = os.getenv("AMADEUS_CLIENT_SECRET", "").strip()
AMADEUS_ENV = os.getenv("AMADEUS_ENV", "test").strip().lower()

KIWI_API_KEY = os.getenv("KIWI_API_KEY", "").strip()

# RapidAPI Skyscanner keys (supports multiple keys separated by comma for rotation)
_rapid_keys_raw = os.getenv("RAPIDAPI_KEYS", os.getenv("RAPIDAPI_KEY", "")).strip()
RAPIDAPI_KEYS = [k.strip() for k in _rapid_keys_raw.split(",") if k.strip()]
RAPIDAPI_KEY = RAPIDAPI_KEYS[0] if RAPIDAPI_KEYS else ""
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "flights-sky.p.rapidapi.com").strip()

# Google Flights keys (supports multiple keys separated by comma for rotation)
_gflight_keys_raw = os.getenv(
    "GOOGLE_FLIGHTS_API_KEYS",
    os.getenv("GOOGLE_FLIGHTS_API_KEY", os.getenv("RAPIDAPI_KEY", "")),
).strip()
GOOGLE_FLIGHTS_API_KEYS = [k.strip() for k in _gflight_keys_raw.split(",") if k.strip()]
GOOGLE_FLIGHTS_API_KEY = GOOGLE_FLIGHTS_API_KEYS[0] if GOOGLE_FLIGHTS_API_KEYS else ""
GOOGLE_FLIGHTS_HOST = os.getenv("GOOGLE_FLIGHTS_HOST", "google-flights2.p.rapidapi.com").strip()

# Skyscanner Flights 4 (skyscanner-flights4.p.rapidapi.com - 100 free requests/month)
_skyscanner4_keys_raw = os.getenv(
    "SKYSCANNER4_API_KEYS",
    os.getenv("SKYSCANNER4_API_KEY", os.getenv("RAPIDAPI_KEY", "")),
).strip()
SKYSCANNER4_API_KEYS = [k.strip() for k in _skyscanner4_keys_raw.split(",") if k.strip()]
SKYSCANNER4_API_KEY = SKYSCANNER4_API_KEYS[0] if SKYSCANNER4_API_KEYS else ""
SKYSCANNER4_HOST = os.getenv("SKYSCANNER4_HOST", "skyscanner-flights4.p.rapidapi.com").strip()

# Flights Scraper Data (flights-scraper-data.p.rapidapi.com - 150 free requests/month)
FLIGHTS_SCRAPER_API_KEY = os.getenv("FLIGHTS_SCRAPER_API_KEY", os.getenv("RAPIDAPI_KEY", "")).strip()
FLIGHTS_SCRAPER_HOST = os.getenv("FLIGHTS_SCRAPER_HOST", "flights-scraper-data.p.rapidapi.com").strip()

# Kiwi RapidAPI (kiwi-com-cheap-flights.p.rapidapi.com)
KIWI_RAPID_API_KEY = os.getenv("KIWI_RAPID_API_KEY", os.getenv("RAPIDAPI_KEY", "")).strip()
KIWI_RAPID_HOST = os.getenv("KIWI_RAPID_HOST", "kiwi-com-cheap-flights.p.rapidapi.com").strip()

# AeroDataBox (aerodatabox.p.rapidapi.com - 1600 calls/month)
AERODATABOX_API_KEY = os.getenv("AERODATABOX_API_KEY", os.getenv("RAPIDAPI_KEY", "")).strip()
AERODATABOX_HOST = os.getenv("AERODATABOX_HOST", "aerodatabox.p.rapidapi.com").strip()

# Multi Site Flight Search (multi-site-flight-search.p.rapidapi.com)
MULTI_SITE_API_KEY = os.getenv("MULTI_SITE_API_KEY", os.getenv("RAPIDAPI_KEY", "")).strip()
MULTI_SITE_HOST = os.getenv("MULTI_SITE_HOST", "multi-site-flight-search.p.rapidapi.com").strip()

DUFFEL_API_KEY = os.getenv("DUFFEL_API_KEY", "").strip()

# Flight Provider selection: "auto", "pool", "google", "skyscanner4", "rapidapi", "kiwi", "duffel", "amadeus", "mock"
FLIGHT_PROVIDER = os.getenv("FLIGHT_PROVIDER", "auto").strip().lower()

# Database & Cache
CACHE_DB_PATH = os.getenv("CACHE_DB_PATH", str(BASE_DIR / "vusca_cache.db"))
CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", "48"))

# Default PTO / Holidays
DEFAULT_COUNTRY = os.getenv("DEFAULT_COUNTRY", "ES").upper()
DEFAULT_SUBDIV = os.getenv("DEFAULT_SUBDIV", "MD").upper()

# Rate limiting defaults (seconds between API calls to stay within free tier)
DEFAULT_API_DELAY_SECONDS = float(os.getenv("DEFAULT_API_DELAY_SECONDS", "0.05"))
SEARCH_CONCURRENCY = int(os.getenv("SEARCH_CONCURRENCY", "8"))

# Pre-configured Search Presets
SEARCH_PRESETS = {
    "bilbao_europe_japan": {
        "origins": ["BIO", "MAD"],
        "destinations": ["TYO", "OSA"],
        "return_destinations": ["TYO", "OSA"],
        "return_arrivals": ["BIO", "MAD"],
        "stopovers": ["FRA", "MUC", "CDG", "AMS", "IST", "HEL", "ZRH", "LHR", "ICN", "SIN"],
        "event": "semana-santa",
        "year": 2027,
        "min_trip_days": 18,
        "max_trip_days": 26,
        "days_pto": 15,
        "date_flexibility": 2,
        "priority": "balanced",
        "subdivision": "PV",
    },
    "japan_super_ampliada": {
        "origins": ["MAD", "BIO"],
        "destinations": ["TYO", "OSA", "NGO", "FUK", "CTS", "OKA"],
        "return_destinations": ["TYO", "OSA", "NGO", "FUK", "CTS", "OKA"],
        "return_arrivals": ["MAD", "BIO"],
        "stopovers": ["IST", "DOH", "DXB", "AUH", "ICN", "HKG", "TPE", "BKK", "SIN", "KUL", "HAN", "HEL"],
        "event": "semana-santa",
        "year": 2027,
        "min_trip_days": 20,
        "max_trip_days": 26,
        "days_pto": 15,
        "date_flexibility": 2,
        "priority": "balanced",
        "subdivision": "PV",
    },
    "malaysia_singapore": {
        "origins": ["MAD", "BIO"],
        "destinations": ["KUL", "SIN"],
        "return_destinations": ["KUL", "SIN"],
        "return_arrivals": ["MAD", "BIO"],
        "stopovers": ["DOH", "DXB", "IST", "BKK"],
        "event": "semana-santa",
        "year": 2027,
        "min_trip_days": 20,
        "max_trip_days": 25,
        "days_pto": 12,
        "date_flexibility": 2,
        "priority": "balanced",
    },
    "colombia_caribe": {
        "origins": ["MAD", "BIO"],
        "destinations": ["BOG"],
        "return_destinations": ["BOG", "CTG"],
        "return_arrivals": ["MAD", "BIO"],
        "stopovers": ["SDQ", "PTY", "MIA"],
        "event": "pilar",
        "year": 2026,
        "min_trip_days": 14,
        "max_trip_days": 17,
        "days_pto": 9,
        "date_flexibility": 1,
        "priority": "balanced",
    },
}
