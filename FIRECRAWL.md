# Firecrawl Setup & Usage

[Firecrawl](https://firecrawl.dev) provides web search, scraping, page
interaction, document parsing, and monitoring for this project (e.g. pulling
market news, filings, or reference pages into the Quant Dashboard).

## Setup (one-time)

```bash
# Install the CLI
npm install -g firecrawl-cli

# Authenticate (get a key at https://www.firecrawl.dev)
firecrawl login --api-key "$FIRECRAWL_API_KEY"

# Verify
firecrawl --status
```

For code that calls the API, copy `.env.example` to `.env` and set your key:

```dotenv
FIRECRAWL_API_KEY=fc-...
```

`.env` and the CLI's local cache directory `.firecrawl/` are gitignored —
never commit a real API key.

## CLI usage

```bash
# Scrape a URL to clean markdown (main content only)
firecrawl scrape https://example.com --only-main-content -o .firecrawl/page.md

# Search the web
firecrawl search "S&P 500 earnings calendar"

# Interact with pages that need clicks/forms/login
firecrawl interact https://example.com

# Parse a local document (PDF, DOCX, XLSX, ...)
firecrawl parse ./report.pdf -o .firecrawl/report.md

# Monitor a page for changes on a schedule
firecrawl monitor create --url https://example.com --goal "notify on new filings" --schedule "every 30 minutes"
```

Recommended flow: **search** to discover pages → **scrape** once you have a
URL → **interact** only when a page needs clicks or login → **parse** for
local files → **monitor** when the same URL needs checking repeatedly.

## API usage (from code)

Base URL `https://api.firecrawl.dev/v2`, header
`Authorization: Bearer $FIRECRAWL_API_KEY`. Key endpoints: `POST /search`,
`POST /scrape`, `POST /interact`, `POST /parse`, `POST /monitor`.
Full reference: https://docs.firecrawl.dev

Example:

```bash
curl -X POST https://api.firecrawl.dev/v2/scrape \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "onlyMainContent": true}'
```

## Known environment caveats

- **Corporate/agent proxies:** the CLI (v1.19.x) bundles axios < 1.16.1 in
  its `firecrawl` SDK dependency, which sends plain-HTTP requests to HTTPS
  proxies and fails with `405 Method Not Allowed`. Fix: upgrade the nested
  copy at
  `$(npm root -g)/firecrawl-cli/node_modules/firecrawl/node_modules/axios`
  to axios ≥ 1.16.1.
- If the proxy then returns `403` on CONNECT to `api.firecrawl.dev:443`,
  the host is blocked by the network egress policy and must be allowlisted
  by an admin.
