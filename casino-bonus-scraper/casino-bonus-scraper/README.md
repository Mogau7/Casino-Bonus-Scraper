# Fine Print: casino bonus scraper

A script reads one public comparison page, a language model turns the free-text terms into structured fields, and a single web page shows the result.

- Source: one public page (set in `SOURCE_URL` at the top of `scrape.py`). It reads the first 3 casinos from the comparison table.
- Fields per casino: welcome bonus, wagering requirement (as a multiplier), minimum deposit, source URL.
- Language model step: Claude (Haiku by default) fills a fixed form for each table row. If a value is not in the text it returns null, and the script also drops any number that does not appear in the row.
- Output: `data/casinos.json`. The page `index.html` builds its table from that file.

## Run it on your computer
Needs Python 3.9 or newer and an Anthropic API key. There is nothing to install: the script only uses the standard library.

    export ANTHROPIC_API_KEY=your-key      # Windows PowerShell: $env:ANTHROPIC_API_KEY="your-key"
    python scrape.py --serve

That writes `data/casinos.json`, prints the three rows, then serves the page at http://localhost:8000. Leave off `--serve` to only write the file.

## Publish it (GitHub does everything after one setup)
1. Push this repo to GitHub.
2. Settings, Secrets and variables, Actions, New repository secret. Name it `ANTHROPIC_API_KEY` and paste your key.
3. Settings, Pages, Deploy from a branch, branch `main`, folder `/ (root)`.
4. Actions tab, "Update bonuses", Run workflow.

The workflow runs the tests, runs the scraper, and commits `data/casinos.json` back to the repo. GitHub Pages then updates the page within a minute. It repeats every day at 05:17 UTC. If a run fails (blocked source, bad key, broken table), the run turns red and GitHub emails you, and the page shows an "older than 3 days" note until it recovers.
Your page is at `https://YOUR-NAME.github.io/REPO-NAME/`.

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
