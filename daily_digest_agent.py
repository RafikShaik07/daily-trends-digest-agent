"""
Daily Trends Digest Agent (Gemini + tool use)

Industry: Technology news.  Brand: a consumer gadgets store (change BRAND below).

How it works (an agent = a model that decides which tools to call):
  1. The model is given ONE tool: fetch_feed(feed_name).
  2. It calls the tool for each of the 5 RSS feeds listed in feeds.json.
  3. Our code downloads and parses the feed and returns the latest headlines.
  4. After reading all 5 feeds, the model writes a 5-bullet digest with
     source links and a social-media post idea for the brand.
  5. We print the digest and save it to digests/digest-YYYY-MM-DD.md

Setup:
    pip install google-genai
    set GEMINI_API_KEY=your-key          (Mac/Linux: export GEMINI_API_KEY="your-key")
Run:
    python daily_digest_agent.py
"""

import datetime
import html
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

MODEL = os.environ.get("MODEL", "gemini-3.8-flash")
BRAND = os.environ.get("BRAND", "a consumer gadgets and electronics store")
HERE = os.path.dirname(os.path.abspath(__file__))
FEEDS_FILE = os.path.join(HERE, "feeds.json")
OUT_DIR = os.path.join(HERE, "digests")
ITEMS_PER_FEED = 8
MAX_STEPS = 12  # safety limit so the loop can never run forever


# ---------------------------------------------------------------------------
# RSS / Atom reading (standard library only)
# ---------------------------------------------------------------------------
def _local(tag: str) -> str:
    """Strip the XML namespace from a tag name: '{ns}title' -> 'title'."""
    return tag.rsplit("}", 1)[-1]


def _clean(text: str, limit: int = 220) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")        # remove HTML tags
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text[:limit]


def parse_feed(xml_bytes: bytes, limit: int = ITEMS_PER_FEED) -> list:
    """Parse RSS 2.0 or Atom XML into a list of {title, link, summary, published}."""
    root = ET.fromstring(xml_bytes)
    items = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        entry = {"title": "", "link": "", "summary": "", "published": ""}
        for child in node:
            name = _local(child.tag)
            if name == "title":
                entry["title"] = _clean(child.text, 200)
            elif name == "link":
                entry["link"] = (child.get("href") or child.text or "").strip()
            elif name in ("description", "summary", "content") and not entry["summary"]:
                entry["summary"] = _clean(child.text)
            elif name in ("pubDate", "published", "updated") and not entry["published"]:
                entry["published"] = (child.text or "").strip()
        if entry["title"] and entry["link"]:
            items.append(entry)
        if len(items) >= limit:
            break
    return items


def load_feeds() -> dict:
    with open(FEEDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# The tool the AI can call
# ---------------------------------------------------------------------------
def fetch_feed(feed_name: str) -> dict:
    feeds = load_feeds()
    if feed_name not in feeds:
        return {"error": f"Unknown feed '{feed_name}'", "available_feeds": list(feeds)}
    try:
        req = urllib.request.Request(
            feeds[feed_name], headers={"User-Agent": "Mozilla/5.0 (daily-digest-agent)"}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        return {"feed": feed_name, "items": parse_feed(data)}
    except Exception as e:  # one broken feed must not stop the whole digest
        return {"feed": feed_name, "error": f"Could not read feed: {e}"}


def build_config(feed_names: list) -> types.GenerateContentConfig:
    tool = types.Tool(
        function_declarations=[
            {
                "name": "fetch_feed",
                "description": "Fetch the latest headlines (title, link, summary, date) from one news RSS feed.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "feed_name": {
                            "type": "string",
                            "enum": feed_names,
                            "description": "Name of the news feed to read",
                        }
                    },
                    "required": ["feed_name"],
                },
            }
        ]
    )
    system = (
        f"You are a social media research assistant for {BRAND}. "
        f"Today is {datetime.date.today():%A, %d %B %Y}. "
        "Read EVERY feed using the fetch_feed tool (one call per feed). "
        "Then write a daily digest in Markdown with exactly 5 bullets: the 5 most "
        "relevant and interesting stories for this brand's audience. "
        "Each bullet must have: a bold headline, a one-sentence summary, "
        "'Source:' followed by the article link, and 'Post idea:' with a short, "
        "specific idea the brand could post (format + hook). "
        "Only use links returned by the tool. Never invent stories or links. "
        "If a feed failed, ignore it and use the others. "
        "Start with a title line '# Daily Tech Digest - <date>' and end after the 5th bullet."
    )
    return types.GenerateContentConfig(
        system_instruction=system,
        tools=[tool],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def call_model(client, contents, config):
    """Call the model, retrying if Google's server is busy (503) or rate limited (429)."""
    for attempt in range(5):
        try:
            return client.models.generate_content(model=MODEL, contents=contents, config=config)
        except (genai_errors.ServerError, genai_errors.ClientError) as e:
            if getattr(e, "code", None) not in (429, 503) or attempt == 4:
                raise
            wait = 5 * (attempt + 1)
            print(f"[server busy, retrying in {wait}s...]")
            time.sleep(wait)


# ---------------------------------------------------------------------------
# The agent loop
# ---------------------------------------------------------------------------
def run_agent() -> str:
    client = genai.Client()  # reads GEMINI_API_KEY from the environment
    feed_names = list(load_feeds())
    config = build_config(feed_names)
    contents = [
        types.Content(
            role="user",
            parts=[types.Part(text="Create today's digest: read all the feeds, then write the 5-bullet digest.")],
        )
    ]

    for _ in range(MAX_STEPS):
        response = call_model(client, contents, config)

        if not response.function_calls:          # no more tool requests -> final answer
            return response.text

        contents.append(response.candidates[0].content)   # keep the model's request

        result_parts = []
        for call in response.function_calls:     # the model may ask for several feeds at once
            name = call.args.get("feed_name", "")
            result = fetch_feed(name)
            count = len(result.get("items", []))
            print(f"[tool call] fetch_feed({name!r}) -> {count} items" + (f"  ({result['error']})" if "error" in result else ""))
            result_parts.append(
                types.Part.from_function_response(name=call.name, response={"result": result})
            )
        contents.append(types.Content(role="user", parts=result_parts))

    raise RuntimeError("Agent did not finish within the step limit")


def save_digest(text: str) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"digest-{datetime.date.today():%Y-%m-%d}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text.strip() + "\n")
    return path


if __name__ == "__main__":
    digest = run_agent()
    print("\n" + digest)
    print(f"\nSaved to {save_digest(digest)}")
