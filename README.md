## How the parts connect
- `scrape.py` writes `data/casinos.json`.
- `index.html` reads that same file and builds the table. A test checks that every field the scraper writes is one the page reads.
- `.github/workflows/update.yml` runs the scraper daily and commits the file.
- GitHub Pages serves the repo, so the page always shows the latest commit.

## How it behaves
- It requests the site's `robots.txt` first and stops if the page is not allowed, or if robots.txt cannot be read.
- It makes two requests in total (robots.txt and the page), and says who it is in the User-Agent.
- If the site answers 401, 403, 429 or 503, or serves a CAPTCHA page, it stops and tells you. It never tries to get around a block. To switch source, change `SOURCE_URL`. The table finder expects an HTML table with a "Casino" column header.
- Exit codes: 0 done, 1 failed, 2 blocked by the source.

## Tests

    python -m unittest test_scrape

They run offline against a local test server and a fake model API. They cover robots.txt, blocks, table parsing, the model call and its retries, the checks on the model's answer, the link between the scraper's output and the page, and the local server option. The test page and names in `test_scrape.py` are test fixtures, not output.

## Known limits
- `data/casinos.json` starts empty. The first workflow run (or `python scrape.py`) fills it.
- One page, one table layout. A redesign of the source page can break the table finder.
- Wagering is the multiplier on the main welcome bonus as stated in the row. Rows that give no multiplier show a dash.
- Check the source site's terms of use as well as robots.txt before running this on a schedule.
