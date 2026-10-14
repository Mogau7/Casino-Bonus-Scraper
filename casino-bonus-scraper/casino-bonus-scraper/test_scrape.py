import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import scrape

PAGE = """<html><head><title>Best casino bonuses</title><style>td{color:red}</style></head><body>
<table><tr><th>Nav</th><th>Other</th></tr><tr><td>x</td><td>y</td></tr></table>
<table>
<tr><th>Casino</th><th>Code</th><th>Offer</th><th>Key Terms</th></tr>
<tr><td><b>Alpha Casino Bonus</b></td><td><a href="/go">ALPHA25 - Click To Claim</a></td><td>100% Deposit Match up to $2500 + 100 Bonus Spins</td><td>&bull; 15&times; wagering on deposit match; minimum deposit: $10<br>&bull; Spins valid 7 days</td></tr>
<tr><td>Beta Casino Offer</td><td>BETA</td><td>First deposit matched up to $1,000</td><td>&bull; Minimum deposit: $20<br>&bull; 20&times; wagering</td></tr>
<tr><td>Gamma Casino Promo</td><td>GAMMA</td><td>500 Bonus Spins</td><td>&bull; Credit expires in 7 days</td></tr>
<tr><td>Delta Casino</td><td>DELTA</td><td>Fourth row, should be ignored</td><td>&bull; Minimum deposit: $5</td></tr>
</table></body></html>"""


class Site(BaseHTTPRequestHandler):
    robots = "User-agent: *\nAllow: /\n"
    robots_status = 200
    page = PAGE
    page_status = 200

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/robots.txt":
            body, status = Site.robots, Site.robots_status
        else:
            body, status = Site.page, Site.page_status
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())


class FakeModelApi(BaseHTTPRequestHandler):
    calls = []
    fail_first = 0
    status = 200

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeModelApi.calls.append(({k.lower(): v for k, v in self.headers.items()}, body))
        if FakeModelApi.status != 200:
            self.send_response(FakeModelApi.status)
            self.end_headers()
            return
        if FakeModelApi.fail_first > 0:
            FakeModelApi.fail_first -= 1
            self.send_response(429)
            self.end_headers()
            return
        text = body["messages"][0]["content"]
        answer = fake_extract(text)
        payload = json.dumps({"content": [{"type": "tool_use", "name": "record_bonus", "input": answer}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)


def fake_extract(text):
    name = text.split("Casino: ")[1].split("\n")[0]
    offer = text.split("Offer: ")[1].split("\n")[0]
    wager = None
    found = scrape.re.search(r"(\d+)\u00d7 wagering|(\d+). wagering|(\d+)x", text)
    if found:
        wager = float(next(g for g in found.groups() if g))
    deposit = scrape.re.search(r"minimum deposit: (\$\d+)", text, scrape.re.I)
    return {"casino": name.replace(" Casino Bonus", "").replace(" Casino Offer", "").replace(" Casino Promo", "").replace(" Casino", ""),
            "welcome_bonus": offer, "wagering_multiplier": wager, "min_deposit": deposit.group(1) if deposit else None}


def serve(handler):
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


class ScraperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site, cls.base = serve(Site)
        cls.api, cls.api_base = serve(FakeModelApi)

    @classmethod
    def tearDownClass(cls):
        for server in (cls.site, cls.api):
            server.shutdown()
            server.server_close()

    def setUp(self):
        Site.robots, Site.robots_status, Site.page, Site.page_status = "User-agent: *\nAllow: /\n", 200, PAGE, 200
        FakeModelApi.calls, FakeModelApi.fail_first, FakeModelApi.status = [], 0, 200
        self.tmp = tempfile.TemporaryDirectory()
        self.out = os.path.join(self.tmp.name, "data", "casinos.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_table_picks_the_casino_table_and_first_rows(self):
        rows = scrape.casino_rows(PAGE, 3)
        self.assertEqual(len(rows), 3)
        self.assertIn("Casino: Alpha Casino Bonus", rows[0])
        self.assertIn("15\u00d7 wagering on deposit match; minimum deposit: $10 | \u2022 Spins valid 7 days", rows[0])
        self.assertNotIn("td{color", rows[0])

    def test_no_table_is_an_error(self):
        with self.assertRaises(RuntimeError):
            scrape.casino_rows("<html><body><p>nothing</p></body></html>", 3)

    def test_clean_item_coerces_and_guards(self):
        text = "Casino: A\nOffer: 100% up to $500\nKey Terms: 35x wagering | minimum deposit: $20"
        raw = {"casino": " A ", "welcome_bonus": "100% up to $500", "wagering_multiplier": "35x", "min_deposit": "$20"}
        item = scrape.clean_item(raw, "https://example.test/p", text)
        self.assertEqual((item["name"], item["wagering_multiplier"], item["min_deposit"]), ("A", 35, "$20"))
        invented = scrape.clean_item(dict(raw, wagering_multiplier=99, min_deposit="$999"), "u", text)
        self.assertEqual((invented["wagering_multiplier"], invented["min_deposit"]), (None, None))
        self.assertIsNone(scrape.clean_item(dict(raw, wagering_multiplier=True), "u", text)["wagering_multiplier"])
        self.assertIsNone(scrape.clean_item(dict(raw, wagering_multiplier=-5), "u", text)["wagering_multiplier"])
        for bad in (None, [], {"casino": "A"}, {"welcome_bonus": "x"}):
            with self.assertRaises(ValueError):
                scrape.clean_item(bad, "u", text)

    def test_robots_allows_and_blocks(self):
        scrape.check_robots(self.base + "/page")
        Site.robots = "User-agent: *\nDisallow: /page\n"
        with self.assertRaises(scrape.Blocked):
            scrape.check_robots(self.base + "/page")
        Site.robots = "User-agent: bonus-screening-scraper\nDisallow: /\n"
        with self.assertRaises(scrape.Blocked):
            scrape.check_robots(self.base + "/page")

    def test_missing_robots_is_allowed_but_forbidden_is_not(self):
        Site.robots_status = 404
        scrape.check_robots(self.base + "/page")
        Site.robots_status = 403
        with self.assertRaises(scrape.Blocked):
            scrape.check_robots(self.base + "/page")

    def test_blocks_are_reported_not_bypassed(self):
        Site.page_status = 403
        with self.assertRaises(scrape.Blocked):
            scrape.fetch_page(self.base + "/page")
        Site.page_status, Site.page = 200, "<html><head><title>Just a moment...</title></head></html>"
        with self.assertRaises(scrape.Blocked):
            scrape.fetch_page(self.base + "/page")
        Site.page_status = 500
        with self.assertRaises(RuntimeError):
            scrape.fetch_page(self.base + "/page")

    def test_run_writes_three_casinos(self):
        result = scrape.run(self.base + "/page", 3, ask=fake_extract, output=self.out)
        with open(self.out, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data, result)
        self.assertEqual([c["name"] for c in data["casinos"]], ["Alpha", "Beta", "Gamma"])
        self.assertEqual([c["wagering_multiplier"] for c in data["casinos"]], [15, 20, None])
        self.assertEqual([c["min_deposit"] for c in data["casinos"]], ["$10", "$20", None])
        self.assertTrue(all(c["source_url"] == self.base + "/page" for c in data["casinos"]))
        self.assertFalse(os.path.exists(self.out + ".tmp"))

    def test_run_stops_before_fetching_when_robots_disallow(self):
        Site.robots = "User-agent: *\nDisallow: /\n"
        with self.assertRaises(scrape.Blocked):
            scrape.run(self.base + "/page", 3, ask=fake_extract, output=self.out)
        self.assertFalse(os.path.exists(self.out))

    def test_run_retries_unusable_answers_once_then_fails(self):
        answers = iter([{"casino": "Alpha"}, fake_extract(scrape.casino_rows(PAGE, 3)[0])] + [fake_extract(r) for r in scrape.casino_rows(PAGE, 3)[1:]])
        result = scrape.run(self.base + "/page", 3, ask=lambda text: next(answers), output=self.out)
        self.assertEqual(len(result["casinos"]), 3)
        with self.assertRaises(RuntimeError):
            scrape.run(self.base + "/page", 3, ask=lambda text: {"casino": "x"}, output=self.out)

    def test_model_call_shape_and_retry(self):
        scrape.API_URL = self.api_base + "/v1/messages"
        FakeModelApi.fail_first = 1
        text = scrape.casino_rows(PAGE, 3)[0]
        scrape.time.sleep = lambda s: None
        answer = scrape.ask_model(text, "test-key")
        self.assertEqual(answer["casino"], "Alpha")
        headers, body = FakeModelApi.calls[-1]
        self.assertEqual(headers["x-api-key"], "test-key")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertEqual(body["tool_choice"], {"type": "tool", "name": "record_bonus"})
        self.assertEqual(body["tools"][0]["name"], "record_bonus")
        self.assertEqual(len(FakeModelApi.calls), 2)

    def test_model_errors_are_clear(self):
        scrape.API_URL = self.api_base + "/v1/messages"
        FakeModelApi.status = 401
        with self.assertRaises(RuntimeError) as caught:
            scrape.ask_model("Casino: A\nOffer: x", "bad")
        self.assertIn("401", str(caught.exception))

    def test_full_run_through_the_real_http_path(self):
        scrape.API_URL = self.api_base + "/v1/messages"
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        result = scrape.run(self.base + "/page", 3, output=self.out)
        self.assertEqual(len(result["casinos"]), 3)

    def test_main_exit_codes(self):
        scrape.SOURCE_URL = self.base + "/page"
        scrape.OUTPUT = self.out
        original = scrape.run
        scrape.run = lambda: original(scrape.SOURCE_URL, 3, ask=fake_extract, output=self.out)
        self.assertEqual(scrape.main(), 0)
        Site.robots = "User-agent: *\nDisallow: /\n"
        self.assertEqual(scrape.main(), 2)
        Site.robots = "User-agent: *\nAllow: /\n"
        Site.page = "<html></html>"
        self.assertEqual(scrape.main(), 1)
        scrape.run = original


if __name__ == "__main__":
    unittest.main()
