import os
import time
import json
import hashlib
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential

from services.gpt_client import analyze_news_sentiment


# =========================
# Configuration
# =========================

load_dotenv()

AZURE_KEY = os.getenv("AZURE_KEY")
AZURE_ENDPOINT = os.getenv("AZURE_ENDPOINT")

if not AZURE_KEY or not AZURE_ENDPOINT:
    raise RuntimeError("AZURE_KEY or AZURE_ENDPOINT is missing")

CACHE_EXPIRATION_HOURS = 6
NEWS_CACHE_FILE = "news_cache.json"
API_CALL_COOLDOWN = 60  # seconds
AZURE_BATCH_SIZE = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

client = TextAnalyticsClient(
    endpoint=AZURE_ENDPOINT,
    credential=AzureKeyCredential(AZURE_KEY)
)

# =========================
# Runtime State
# =========================

news_cache: Dict[str, Dict] = {}
LAST_API_CALL_TIME = 0.0


# =========================
# Cache Utilities
# =========================

def load_cache() -> None:
    global news_cache
    if not os.path.exists(NEWS_CACHE_FILE):
        news_cache = {}
        return

    try:
        with open(NEWS_CACHE_FILE, "r", encoding="utf-8") as f:
            news_cache = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load cache: {e}")
        news_cache = {}


def save_cache() -> None:
    try:
        with open(NEWS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(news_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Failed to save cache: {e}")


load_cache()


def generate_cache_key(url: str, titles: List[str]) -> str:
    content_hash = hashlib.md5(
        "|".join(titles).encode("utf-8")
    ).hexdigest()
    return f"{url}:{content_hash}"


def get_cached_response(key: str) -> Optional[List[Dict]]:
    entry = news_cache.get(key)
    if not entry:
        return None

    expiry = datetime.fromtimestamp(entry["timestamp"]) + timedelta(hours=CACHE_EXPIRATION_HOURS)
    if datetime.utcnow() > expiry:
        return None

    return entry["data"]


# =========================
# Azure Sentiment
# =========================

def analyze_sentiment(titles: List[str]) -> List[Dict]:
    results: List[Dict] = []

    for i in range(0, len(titles), AZURE_BATCH_SIZE):
        batch = titles[i:i + AZURE_BATCH_SIZE]

        try:
            response = client.analyze_sentiment(batch, language="en")
            for doc in response:
                results.append({
                    "label": doc.sentiment,
                    "confidence_scores": {
                        "positive": doc.confidence_scores.positive,
                        "neutral": doc.confidence_scores.neutral,
                        "negative": doc.confidence_scores.negative
                    }
                })
        except Exception as e:
            logging.error(f"Azure sentiment batch failed: {e}")
            results.extend([{}] * len(batch))

    return results


# =========================
# GPT Parsing
# =========================

def clean_explanation(text: str) -> str:
    unwanted_prefixes = [
        "Certainly!",
        "Here's my analysis",
        "Market analysis:",
        "Market interpretation:",
        "**Interpretation:**"
    ]

    for prefix in unwanted_prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()

    if text.count("**") >= 2:
        parts = text.split("**")
        if len(parts[1].split()) <= 15:
            text = "".join(parts[2:]).strip()

    return text


def parse_gpt_response(response: str, expected_count: int) -> List[str]:
    explanations: List[str] = []
    current = ""

    for line in response.splitlines():
        line = line.strip()
        if not line:
            continue

        if line[0].isdigit() and ". " in line[:4]:
            if current:
                explanations.append(clean_explanation(current))
            current = line.split(". ", 1)[1]
        else:
            current += f" {line}"

    if current:
        explanations.append(clean_explanation(current))

    while len(explanations) < expected_count:
        explanations.append("No analysis available.")

    return explanations[:expected_count]


# =========================
# GPT Sentiment
# =========================

def get_gpt_analysis(
    titles: List[str]
) -> Tuple[str, List[str]]:
    global LAST_API_CALL_TIME

    now = time.time()
    if now - LAST_API_CALL_TIME < API_CALL_COOLDOWN:
        logging.warning("GPT API cooldown active")
        return "Rate limited", ["Rate limited"] * len(titles)

    try:
        LAST_API_CALL_TIME = now
        raw = analyze_news_sentiment(titles)
        parsed = parse_gpt_response(raw, len(titles))
        return raw, parsed
    except Exception as e:
        logging.error(f"GPT analysis failed: {e}")
        return "GPT error", ["Unable to analyze"] * len(titles)


# =========================
# Main Entry
# =========================

def fetch_and_analyze_news_by_url(url: str) -> Dict:
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logging.error(f"Failed fetching news: {e}")
        return {"error": str(e)}

    articles = data.get("articles")
    if not articles:
        return {"error": "No articles found"}

    titles = [a.get("title", "") for a in articles]
    descriptions = [a.get("description", "") for a in articles]
    contents = [
        f"{d}\n{a.get('content', '')}".strip()
        for d, a in zip(descriptions, articles)
    ]

    cache_key = generate_cache_key(url, titles)
    cached = get_cached_response(cache_key)
    if cached:
        logging.info("Serving from cache")
        return {"articles": cached}

    azure_results = analyze_sentiment(titles)
    _, gpt_results = get_gpt_analysis(titles)

    for i, article in enumerate(articles):
        article["azure_sentiment"] = azure_results[i] if i < len(azure_results) else {}
        article["gpt_analysis"] = gpt_results[i] if i < len(gpt_results) else ""

    news_cache[cache_key] = {
        "timestamp": time.time(),
        "data": articles
    }
    save_cache()

    return {"articles": articles}
