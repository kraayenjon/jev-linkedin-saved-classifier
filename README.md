# Jev LinkedIn Saved Classifier

> LinkedIn gives you a saved-posts graveyard. This turns it into a filterable board.

Reads your own **Saved Posts** page from your already-logged-in Chrome, extracts each
post, and classifies every one with [TypeSafe's Jev](https://docs.typesafe.ai) into a
category you define. Output is a CSV, a JSON trace, and a LinkedIn-styled HTML board you
can search, filter, sort, and preview inline.

Built as a small, honest use of [jev-ultrafast](https://github.com/browser-use/jev-ultrafast)
for the "browser use" layer. Reading is plain DOM code. Classification is one Jev call
per post.

```
n saved posts  ->  scroll the rendered cards  ->  one Jev call each  ->  board + csv + json
```

## Why

LinkedIn lets you save posts but gives you almost no way to find them again: no search,
no tags, no sort, no filter. If you have hundreds of saves, they are effectively lost.
This tool gives them back, with tags you control.

## How it works

1. **Attach, don't automate.** It connects to your existing Chrome tab over CDP via
   `browser-harness`, attaches to the saved-posts tab, and reads the DOM.
2. **Read only.** It extracts author, headline, post text (above the fold), media type,
   post URL, avatar and a media thumbnail. It never opens a post, a profile, or a
   "see more".
3. **Scroll like a person.** Gentle, randomized scroll steps with pauses, so lazy-loaded
   cards appear. A safety cap stops the loop.
4. **Classify with Jev.** One `typesafe-ai/jev` call per post returns a category and a
   confidence score.
5. **Render.** A CSV, a JSON trace, and an HTML board with a LinkedIn-like look: avatar,
   name, headline, post text, media thumbnail, category chip, and an inline embed
   preview.

## Anti-block design

The tool is deliberately conservative, because your account matters more than the data:

- No clicks on posts, profiles, or links. Nothing opens in a new tab.
- No per-post page loads during extraction — only the list you already have open.
- Randomized delays between scrolls (about 1.3–2.9 s).
- Preview embeds load **at most two at a time**, spaced about 0.65 s, only for posts you
  scroll to, and **unload** when you scroll past them. Turn the toggle off for manual-only.
- One long-lived browser connection, one action at a time.

## Requirements

- macOS, Linux, or Windows with Chrome (or a Chromium browser).
- Python 3.12+ and [uv](https://docs.astral.sh/uv/).
- An API key for Jev: a Vercel AI Gateway key (preferred) or a TypeSafe key.

## Install

```bash
git clone https://github.com/kraayenjon/jev-linkedin-saved-classifier
cd jev-linkedin-saved-classifier
uv sync
cp .env.example .env        # then add AI_GATEWAY_API_KEY
```

`uv sync` also fetches `jev-ultrafast`, `browser-harness`, and `httpx`.

## Use

1. In Chrome, open **https://www.linkedin.com/my-items/saved-posts/** and log in.
2. Run:

```bash
uv run jev-linkedin-saved              # read + classify + write csv/html/json
uv run jev-linkedin-saved --serve      # also serve the board at http://127.0.0.1:8777
```

The first run may show Chrome's **"Allow remote debugging?"** popup — click **Allow**.
`browser-harness` keeps the connection for later runs.

Open the board over **http** with `--serve`. The inline LinkedIn embed stays blank on
`file://` because Chrome blocks the embed's third-party cookies there; the board warns
you if you open it the wrong way.

## Options

| Flag | What it does |
| --- | --- |
| `--out DIR` | Output directory (default `runs`). |
| `--tags FILE` | JSON file of `{tag: description}` to replace the default tags. |
| `--limit N` | Classify at most N posts (0 = all). |
| `--load-more` | Click "Show more results" if present, human-paced, then read again. |
| `--max-scrolls N` | Safety cap on scroll steps (default 40). |
| `--no-classify` | Extract only; skip all Jev calls. |
| `--serve` | Serve the output dir over http and open the board. |
| `--port N` | Port for `--serve` (default 8777). |
| `--from-json FILE` | Rebuild csv/html from a previous run's JSON. No browser, no Jev. |
| `--enrich` | With `--from-json`: re-read the live DOM for avatars and thumbnails. No Jev. |

## Custom tags

`--tags tags.json` where the file is an object of tag to description:

```json
{
  "AI & Automation": "AI tools, agents, LLMs, prompts, automation",
  "SEO & Search": "SEO, Google, search ranking, SERP",
  "Growth & Marketing": "growth, ads, funnels, distribution, copy",
  "Other": "none of the above"
}
```

Jev picks the single best tag per post and reports its confidence.

## Output

In the output directory:

- `<stamp>-linkedin-saved.csv` — open in Numbers, Excel, or Google Sheets.
- `<stamp>-linkedin-saved.html` — the board. Serve it with `--serve`.
- `<stamp>-linkedin-saved.json` — every row plus the scroll log, timing, and cost.

Columns: number, category, confidence, author, headline, media type, post age, post text
(above the fold), post URL, author URL, activity URN.

## Cost

Classification is billed per Jev call. A run over ~230 posts costs well under a cent on
the AI Gateway. The JSON records the exact cost. `--no-classify`, `--from-json`, and
`--enrich` make no Jev calls.

## Privacy

Everything stays on your machine. `runs/` is gitignored, and no key is ever committed.
The tool reads only what is already rendered in your own logged-in session. It is not
affiliated with LinkedIn; use it on your own account and within LinkedIn's terms.

## Credits

- [jev-ultrafast](https://github.com/browser-use/jev-ultrafast) and
  [browser-harness](https://github.com/browser-use/browser-harness) by Browser Use.
- Jev by [TypeSafe](https://docs.typesafe.ai).

## License

MIT. See [LICENSE](LICENSE).
