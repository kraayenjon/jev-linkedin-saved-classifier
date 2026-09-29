# Jev LinkedIn Saved Classifier

> LinkedIn gives you a saved-posts graveyard. This turns it into a filterable board.

Reads your own **Saved Posts** page from your already-logged-in Chrome, extracts each
post, and classifies every one with [TypeSafe's Jev](https://docs.typesafe.ai) into a
category you define. Output is a CSV, a JSON trace, and a LinkedIn-styled HTML board you
can search, filter, sort, and preview inline.

Reading is plain DOM code through [browser-harness](https://pypi.org/project/browser-harness/).
Classification is one Jev call per post.

```
open saved posts  ->  read every card  ->  one Jev call each  ->  live dashboard  ->  board + csv + json
```

## Quick start

You need Chrome, [uv](https://docs.astral.sh/uv/getting-started/installation/), and one Jev
key: a [Vercel AI Gateway](https://vercel.com/ai-gateway) key or a TypeSafe key.

```bash
git clone https://github.com/kraayenjon/jev-linkedin-saved-classifier
cd jev-linkedin-saved-classifier
uv run jev-linkedin-saved
```

`uv run` installs Python 3.12+ and every dependency on the first call. The first run then:

1. Asks for your Jev key and saves it to `.env` (gitignored).
2. Shows the default categories. Keep them or type your own. Saved to `categories.json`.
3. Connects to Chrome. The first time, Chrome asks to allow remote debugging
   (`chrome://inspect/#remote-debugging`): tick the box and click **Allow**.
4. Opens your saved-posts page. Log in if LinkedIn asks.
5. Asks you to confirm, then reads every saved post. Keep the LinkedIn tab in front.
6. Opens the live dashboard and classifies each post. The last slide links to your board.

Open the board again later:

```bash
uv run jev-linkedin-saved --open
```

Just want to see it? `uv run jev-linkedin-saved --demo` replays a sample run. No Chrome,
no key.

## Why

LinkedIn lets you save posts but gives you almost no way to find them again: no search,
no tags, no sort, no filter. If you have hundreds of saves, they are effectively lost.
This tool gives them back, with tags you control.

## How it works

1. **Your own browser.** It attaches to your running Chrome over CDP with
   `browser-harness`. No headless browser, no automation flag, your normal session.
2. **Read only.** It extracts author, headline, post text (above the fold), media type,
   post URL, avatar and a media thumbnail. It never opens a post, a profile, or a
   "see more".
3. **Paced like a person.** It scrolls with real mouse-wheel events in uneven steps, and
   presses "Show more results" with a real mouse click, with pauses between every action.
4. **Classify with Jev.** One `typesafe-ai/jev` call per post returns a category, a
   confidence score, and the probability for every category.
5. **Show.** A live dashboard while it runs, then a board you can search, filter, sort and
   preview, plus CSV and JSON.

## Keeping your account safe

The tool is deliberately conservative, because your account matters more than the data:

- The only button it presses is "Show more results". No posts, profiles, or links.
- No per-post page loads and no calls to LinkedIn's API: only the list page you see.
- One action at a time, with random pauses: 1.2–3 s between scrolls, 2.5–5 s after each
  "Show more results", and a longer 5–12 s break every 15 steps.
- The board's preview embeds load at most two at a time, only for posts you scroll to.

No tool can promise LinkedIn will never flag an account. Run it on your own account, not
more than about once a day.

## Options

| Flag | What it does |
| --- | --- |
| `--open` | Open the board of your last run. |
| `--demo` | Replay a sample run on the dashboard. No Chrome, no key. |
| `--limit N` | Only your N most recently saved posts: read and classify N, then stop (0 = all). |
| `--no-classify` | Only read the posts; no Jev calls. |
| `--from-json FILE` | Rebuild csv/html from a run's JSON. No browser, no Jev. |
| `--replay FILE` | Replay a finished run on the dashboard (`--speed S` to fit it in S seconds). |
| `--max-steps N` | Safety cap on read steps (default 600). |
| `--out DIR` | Output directory (default `runs`). |
| `--port N` | Local port for the dashboard (default 8777). |

## Your categories

`categories.json` maps each category to what belongs there. Edit it, or delete it to be
asked again:

```json
{
  "AI & Automation": "AI tools, agents, LLMs, prompts, automation",
  "SEO & Search": "SEO, Google, search ranking, SERP",
  "Other": "none of the above"
}
```

Jev picks the single best category per post and reports its confidence.

## Output

In `runs/`:

- `<stamp>-linkedin-saved.html`: the board. Open it with `--open`; its previews need http.
- `<stamp>-linkedin-saved.csv`: open in Numbers, Excel, or Google Sheets.
- `<stamp>-linkedin-saved.json`: every row plus timing and cost.

## Cost

Classification is billed per Jev call. A run over ~230 posts costs well under a cent.
The JSON records the exact cost. `--no-classify`, `--from-json`, `--demo` and
`--replay` make no Jev calls.

## Privacy

Everything stays on your machine. `runs/`, `.env` and `categories.json` are gitignored.
The tool reads only what is already rendered in your own logged-in session. It is not
affiliated with LinkedIn; use it on your own account and within LinkedIn's terms.

## Credits

- [jev-ultrafast](https://github.com/browser-use/jev-ultrafast) and
  [browser-harness](https://github.com/browser-use/browser-harness) by Browser Use.
- Jev by [TypeSafe](https://docs.typesafe.ai).

## License

MIT. See [LICENSE](LICENSE).
