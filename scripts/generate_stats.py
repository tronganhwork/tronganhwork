"""Generate the profile stat cards (dark and light SVG) from the GitHub GraphQL API.

Run by .github/workflows/profile-stats.yml. Needs GITHUB_TOKEN in the environment.
Uses only the Python standard library.
"""
import json
import os
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

LOGIN = os.environ.get("PROFILE_LOGIN", "tronganhwork")
EXCLUDED_LANGUAGES = {"Jupyter Notebook", "HTML", "CSS"}
TOP_LANGUAGES = 5
OUT_DIR = Path(__file__).resolve().parent.parent / "assets"

QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      totalCount
      nodes {
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

THEMES = {
    "dark": {"bg": "#0d1117", "border": "#30363d", "text": "#e6edf3", "muted": "#8b949e",
             "accent": "#58a6ff", "prompt": "#3fb950", "track": "#21262d"},
    "light": {"bg": "#ffffff", "border": "#d0d7de", "text": "#1f2328", "muted": "#57606a",
              "accent": "#0969da", "prompt": "#1a7f37", "track": "#eaeef2"},
}

MONO = "'JetBrains Mono', 'Cascadia Code', Consolas, Menlo, 'DejaVu Sans Mono', monospace"
SANS = "'Segoe UI', -apple-system, 'Helvetica Neue', Arial, sans-serif"
WIDTH, HEIGHT = 480, 200


def fetch(token):
    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        sys.exit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def streaks(calendar):
    days = [d for week in calendar["weeks"] for d in week["contributionDays"]]
    days.sort(key=lambda d: d["date"])
    active = sum(1 for d in days if d["contributionCount"] > 0)

    longest = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] > 0 else 0
        longest = max(longest, run)

    # The current streak may end yesterday if nothing has been pushed today yet.
    counts = {d["date"]: d["contributionCount"] for d in days}
    day = date.fromisoformat(days[-1]["date"])
    if counts.get(day.isoformat(), 0) == 0:
        day -= timedelta(days=1)
    current = 0
    while counts.get(day.isoformat(), 0) > 0:
        current += 1
        day -= timedelta(days=1)
    return current, longest, active


def top_languages(repos):
    sizes, colors = {}, {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            if name in EXCLUDED_LANGUAGES:
                continue
            sizes[name] = sizes.get(name, 0) + edge["size"]
            colors[name] = edge["node"]["color"] or "#8b949e"
    total = sum(sizes.values())
    if not total:
        return []
    ranked = sorted(sizes.items(), key=lambda item: item[1], reverse=True)
    top = [(name, size / total, colors[name]) for name, size in ranked[:TOP_LANGUAGES]]
    rest = sum(size for _, size in ranked[TOP_LANGUAGES:])
    if rest:
        top.append(("Other", rest / total, "#6e7681"))
    return top


def frame(theme, command, note, body):
    t = THEMES[theme]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="10" fill="{t['bg']}" stroke="{t['border']}"/>
  <text x="24" y="36" font-family="{MONO}" font-size="14"><tspan fill="{t['prompt']}">$</tspan><tspan fill="{t['text']}"> {escape(command)}</tspan></text>
  <text x="{WIDTH - 24}" y="36" font-family="{MONO}" font-size="11" fill="{t['muted']}" text-anchor="end">{escape(note)}</text>
{body}
</svg>
"""


def stats_card(theme, metrics):
    t = THEMES[theme]
    cells = []
    for i, (value, label) in enumerate(metrics):
        x = 24 + (i % 3) * 148
        y = 96 + (i // 3) * 70
        cells.append(
            f'  <text x="{x}" y="{y}" font-family="{SANS}" font-size="28" font-weight="700" fill="{t["text"]}">{escape(value)}</text>\n'
            f'  <text x="{x}" y="{y + 20}" font-family="{MONO}" font-size="12" fill="{t["muted"]}">{escape(label)}</text>'
        )
    return frame(theme, f"gh stats {LOGIN}", "updated daily", "\n".join(cells))


def languages_card(theme, languages):
    t = THEMES[theme]
    parts = [
        '  <clipPath id="bar"><rect x="24" y="58" width="432" height="10" rx="5"/></clipPath>',
        f'  <rect x="24" y="58" width="432" height="10" rx="5" fill="{t["track"]}"/>',
        '  <g clip-path="url(#bar)">',
    ]
    x = 24.0
    for _, share, color in languages:
        width = 432 * share
        parts.append(f'    <rect x="{x:.2f}" y="58" width="{width:.2f}" height="10" fill="{color}"/>')
        x += width
    parts.append("  </g>")
    for i, (name, share, color) in enumerate(languages):
        cx = 30 + (i % 2) * 220
        cy = 104 + (i // 2) * 30
        parts.append(
            f'  <circle cx="{cx}" cy="{cy - 4}" r="5" fill="{color}"/>\n'
            f'  <text x="{cx + 14}" y="{cy}" font-family="{SANS}" font-size="14" fill="{t["text"]}">{escape(name)}'
            f'<tspan fill="{t["muted"]}" font-family="{MONO}" font-size="12"> {share * 100:.1f}%</tspan></text>'
        )
    return frame(theme, "gh lang --top 5", "by code size", "\n".join(parts))


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    user = fetch(token)

    calendar = user["contributionsCollection"]["contributionCalendar"]
    current, longest, active = streaks(calendar)
    repos = user["repositories"]
    metrics = [
        (f"{calendar['totalContributions']:,}", "contributions · 1y"),
        (f"{active:,}", "active days · 1y"),
        (f"{longest:,}", "longest streak"),
        (f"{current:,}", "current streak"),
        (f"{repos['totalCount']:,}", "public repos"),
        (user["createdAt"][:4], "on GitHub since"),
    ]
    languages = top_languages(repos["nodes"])

    OUT_DIR.mkdir(exist_ok=True)
    for theme in THEMES:
        (OUT_DIR / f"stats-{theme}.svg").write_text(stats_card(theme, metrics), encoding="utf-8")
        (OUT_DIR / f"languages-{theme}.svg").write_text(languages_card(theme, languages), encoding="utf-8")
    print("metrics:", metrics)
    print("languages:", [(name, round(share * 100, 1)) for name, share, _ in languages])


if __name__ == "__main__":
    main()
