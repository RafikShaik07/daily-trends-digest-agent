# Daily Trends Digest Agent

An AI agent that reads **5 tech-news RSS feeds** and writes a **daily 5-bullet digest** with **source links** and a **post idea** a brand could publish for each story.

- **Industry:** Technology
- **Example brand:** a consumer gadgets and electronics store (change it with the `BRAND` setting)
- **Built with:** Python + Gemini API (tool use / function calling)

## How the agent works

An agent is an AI model that decides which tools to use. This agent has one tool, `fetch_feed(feed_name)`.

```
Start
  |
  v
[1] Model gets the task + the fetch_feed tool
  |
  v
[2] Model calls fetch_feed for each of the 5 feeds      <-- the model decides this
  |
  v
[3] Our code downloads + parses each RSS feed, returns the latest headlines
  |
  v
[4] Model reads all the headlines and picks the 5 best stories for the brand
  |
  v
[5] Model writes the digest: headline, summary, source link, post idea
  |
  v
[6] Script prints it and saves digests/digest-YYYY-MM-DD.md
```

The loop in `run_agent()` keeps going while the model asks for tools, and stops when it returns the final text. A step limit prevents endless loops, and a broken feed is skipped instead of crashing the agent.

## The 5 feeds (`feeds.json`)

TechCrunch, The Verge, Ars Technica, Wired and Engadget. To use another industry (fashion, food, fitness), replace the names and URLs in `feeds.json` and change the `BRAND` setting.

## Project files

| File | Purpose |
|---|---|
| `daily_digest_agent.py` | The agent, the RSS reader and the tool-use loop |
| `feeds.json` | The 5 RSS feeds |
| `requirements.txt` | Python dependency (`google-genai`) |
| `.github/workflows/daily-digest.yml` | Runs the agent automatically every day |
| `digests/` | Saved daily digests |

## Run it

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="your-key"        # Windows PowerShell: $env:GEMINI_API_KEY="your-key"
python daily_digest_agent.py
```

Optional settings: `MODEL` (Gemini model name) and `BRAND` (who the post ideas are for).

## Run it every day (GitHub Actions)

1. In your GitHub repo go to **Settings → Secrets and variables → Actions → New repository secret**.
2. Name it `GEMINI_API_KEY` and paste your key.
3. The workflow runs every day at 08:00 IST and commits the new file to `digests/`. You can also run it any time from the **Actions** tab with **Run workflow**.

## Output format (illustrative)

The digest follows this shape. The stories below are placeholders to show the layout, not real output.

```markdown
# Daily Tech Digest - <date>

- **<Headline 1>** - <one-sentence summary>.
  Source: <article link>
  Post idea: <format + hook the brand could post>
- **<Headline 2>** ...
  (5 bullets in total)
```

Real digests are saved in the `digests/` folder.

## Notes

- Links come only from the feeds the tool returned, so the model cannot invent URLs.
- Never commit your API key. It is only read from the `GEMINI_API_KEY` environment variable or GitHub secret.
