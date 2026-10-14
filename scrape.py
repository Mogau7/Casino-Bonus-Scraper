import functools
import http.server
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

SOURCE_URL = "https://www.rotowire.com/article/best-casino-bonuses-in-the-us-this-week-top-welcome-offers-for-new-players-in-2026-120013"
HOW_MANY = 3
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "casinos.json")
USER_AGENT = "bonus-screening-scraper/1.0 (hiring screening task; one polite request)"
API_URL = os.environ.get("ANTHROPIC_URL", "https://api.anthropic.com/v1/messages")
MODEL = os.environ.get("MODEL", "claude-haiku-4-5-20251001")

SYSTEM = (
    "You read one row of a casino bonus comparison table and fill in the form. "
    "Use only the text you are given. Never guess: if a value is not stated, return null. "
    "wagering_multiplier is the play-through multiplier on the main welcome bonus, as a plain number (15x means 15). "
    "min_deposit keeps its currency symbol, like $10. "
    "welcome_bonus is short: keep the amounts and spins, drop promo codes and marketing words. "
    "casino is the brand name only, without words like Casino, Bonus, Offer or Promo."
)
TOOL = {
    "name": "record_bonus",
    "description": "Record the structured bonus fields for this casino.",
    "input_schema": {
        "type": "object",
        "properties": {
            "casino": {"type": "string"},
            "welcome_bonus": {"type": "string"},
            "wagering_multiplier": {"type": ["number", "null"]},
            "min_deposit": {"type": ["string", "null"]},
        },
        "required": ["casino", "welcome_bonus", "wagering_multiplier", "min_deposit"],
    },
}


class Blocked(Exception):
    pass


def http_get(url, accept):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.status, response.read().decode(charset, "replace")
    except urllib.error.HTTPError as error:
        return error.code, ""


def check_robots(url):
    parts = urlparse(url)
    status, body = http_get(f"{parts.scheme}://{parts.netloc}/robots.txt", "text/plain")
    if status in (404, 410):
        return
    if status != 200:
        raise Blocked(f"could not read robots.txt (HTTP {status}), so I cannot confirm this page is allowed")
    rules = urllib.robotparser.RobotFileParser()
    rules.parse(body.splitlines())
    if not rules.can_fetch(USER_AGENT, url):
        raise Blocked("robots.txt does not allow this page")


def fetch_page(url):
    status, html = http_get(url, "text/html")
    if status in (401, 403, 429, 503):
        raise Blocked(f"the site answered HTTP {status}, which looks like a block")
    if status != 200:
        raise RuntimeError(f"the page answered HTTP {status}")
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if title and re.search(r"captcha|access denied|attention required|just a moment|verify you are human", title.group(1), re.I):
        raise Blocked("the page is a CAPTCHA or bot check")
    return html


def tidy(text):
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(\s*\|\s*)+", " | ", text)
    return text.strip(" |")


class Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.row = None
        self.cell = None
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag == "br" and self.cell is not None:
            self.cell.append(" | ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(tidy("".join(self.cell)))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.tables[-1].append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None and not self.skip:
            self.cell.append(data)


def casino_rows(html, count):
    parser = Tables()
    parser.feed(html)
    for table in parser.tables:
        if table and any("casino" in cell.lower() for cell in table[0]):
            header = table[0]
            rows = []
            for row in table[1:]:
                if len(row) == len(header) and row[0]:
                    rows.append("\n".join(f"{name}: {value}" for name, value in zip(header, row)))
            if rows:
                return rows[:count]
    raise RuntimeError("no casino table found on the page")


def ask_model(row_text, api_key):
    body = {
        "model": MODEL,
        "max_tokens": 400,
        "system": SYSTEM,
        "tools": [TOOL],
        "tool_choice": {"type": "tool", "name": "record_bonus"},
        "messages": [{"role": "user", "content": row_text}],
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.load(response)
            break
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 502, 503, 529) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"the model API answered HTTP {error.code}") from None
    for block in data.get("content", []):
        if block.get("type") == "tool_use":
            return block["input"]
    raise RuntimeError("the model did not return the form")


def short_text(value, limit):
    if not isinstance(value, str):
        return None
    return re.sub(r"\s+", " ", value).strip()[:limit] or None


def multiplier(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        found = re.search(r"\d+(?:\.\d+)?", value)
        value = float(found.group()) if found else None
    if not isinstance(value, (int, float)) or not 0 < value <= 200:
        return None
    return int(value) if float(value).is_integer() else float(value)


def in_source(value, row_text):
    digits = re.findall(r"\d+(?:\.\d+)?", str(value))
    return bool(digits) and all(d in row_text for d in digits)


def clean_item(raw, url, row_text):
    if not isinstance(raw, dict):
        raise ValueError("the answer was not an object")
    item = {
        "name": short_text(raw.get("casino"), 60),
        "welcome_bonus": short_text(raw.get("welcome_bonus"), 140),
        "wagering_multiplier": multiplier(raw.get("wagering_multiplier")),
        "min_deposit": short_text(raw.get("min_deposit"), 30),
        "source_url": url,
    }
    if not item["name"] or not item["welcome_bonus"]:
        raise ValueError("the answer had no casino name or bonus")
    if item["wagering_multiplier"] is not None and not in_source(item["wagering_multiplier"], row_text):
        item["wagering_multiplier"] = None
    if item["min_deposit"] is not None and not in_source(item["min_deposit"], row_text):
        item["min_deposit"] = None
    return item


def run(url=SOURCE_URL, count=HOW_MANY, ask=None, output=OUTPUT):
    check_robots(url)
    rows = casino_rows(fetch_page(url), count)
    if ask is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise SystemExit("Set ANTHROPIC_API_KEY first. See the README.")
        ask = lambda text: ask_model(text, api_key)
    casinos = []
    for row_text in rows:
        for attempt in (1, 2):
            try:
                casinos.append(clean_item(ask(row_text), url, row_text))
                break
            except ValueError as error:
                if attempt == 2:
                    raise RuntimeError(f"the model kept giving unusable answers: {error}")
    result = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": url, "casinos": casinos}
    os.makedirs(os.path.dirname(output), exist_ok=True)
    temp = output + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(temp, output)
    return result


def make_server(port=8000):
    root = os.path.dirname(os.path.abspath(__file__))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=root)
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    return http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve(port=8000):
    server = make_server(port)
    print(f"Open http://localhost:{server.server_port} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        result = run()
    except Blocked as error:
        print(f"Stopped: {error}. I do not work around blocks. Pick another source in SOURCE_URL.")
        return 2
    except (RuntimeError, urllib.error.URLError, OSError) as error:
        print(f"Failed: {error}")
        return 1
    print(f"Wrote {len(result['casinos'])} casinos to {OUTPUT}")
    for item in result["casinos"]:
        print(f"  {item['name']}: {item['welcome_bonus']} | {item['wagering_multiplier']}x | min {item['min_deposit']}")
    if "--serve" in argv:
        serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
