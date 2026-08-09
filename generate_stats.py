#!/usr/bin/env python3
"""Generate a GitHub-stats SVG card (dracula theme) without any 3rd-party action.
Usage: python3 generate_stats.py [username]
Writes: profile/stats.svg
"""
import json
import os
import sys
import datetime
import urllib.request

USERNAME = os.environ.get("USERNAME") or (sys.argv[1] if len(sys.argv) > 1 else "farzadqavidel")
API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "stats-card"}
TOKEN = os.environ.get("GITHUB_TOKEN")
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"


def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---- fetch user ----
user = get(f"{API}/users/{USERNAME}")
followers = user.get("followers", 0)
following = user.get("following", 0)
public_repos = user.get("public_repos", 0)
name = user.get("name") or USERNAME

# ---- fetch repos (paginated) ----
repos = []
page = 1
while True:
    chunk = get(f"{API}/users/{USERNAME}/repos?per_page=100&page={page}")
    if not chunk:
        break
    repos.extend(chunk)
    if len(chunk) < 100:
        break
    page += 1

total_stars = sum(r.get("stargazers_count", 0) for r in repos)
langs = {}
for r in repos:
    l = r.get("language")
    if l:
        langs[l] = langs.get(l, 0) + 1
top_lang = max(langs, key=langs.get) if langs else "—"

# ---- commits this year (best-effort, external API) ----
year = datetime.date.today().year
commits = "N/A"
try:
    cu = f"https://github-contributions-api.jogruber.de/v4/{USERNAME}?y={year}"
    data = get(cu)
    contributions = data.get("contributions", [])
    commits = sum(c.get("count", 0) for c in contributions)
except Exception:
    commits = "N/A"

# ---- rows ----
rows = [
    ("#ff79c6", "Total Stars Earned", f"{total_stars:,}"),
    ("#f1fa8c", f"Total Commits ({year})", f"{commits:,}" if isinstance(commits, int) else commits),
    ("#8be9fd", "Followers", f"{followers:,}"),
    ("#50fa7b", "Following", f"{following:,}"),
    ("#bd93f9", "Public Repos", f"{public_repos:,}"),
    ("#ffb86c", "Top Language", esc(top_lang)),
]

# ---- svg layout ----
W = 495
row_h = 38
title_y = 42
start_y = 84
H = start_y + len(rows) * row_h + 22

parts = []
parts.append(
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" fill="none">'
)
parts.append(f'<rect x="0.5" y="0.5" rx="14" ry="14" width="{W-1}" height="{H-1}" fill="#282a36"/>')
parts.append(
    f'<text x="25" y="{title_y}" font-family="Segoe UI, Ubuntu, Helvetica, Arial, sans-serif" '
    f'font-size="20" font-weight="700" fill="#f8f8f2">{esc(name)}\'s GitHub Stats</text>'
)

for i, (color, label, value) in enumerate(rows):
    y = start_y + i * row_h
    cy = y - 6
    parts.append(f'<circle cx="30" cy="{cy}" r="6" fill="{color}"/>')
    parts.append(
        f'<text x="48" y="{y}" font-family="Segoe UI, Ubuntu, Helvetica, Arial, sans-serif" '
        f'font-size="15" font-weight="600" fill="{color}">{esc(label)}</text>'
    )
    parts.append(
        f'<text x="{W-25}" y="{y}" font-family="Segoe UI, Ubuntu, Helvetica, Arial, sans-serif" '
        f'font-size="15" font-weight="700" fill="#f8f8f2" text-anchor="end">{value}</text>'
    )

parts.append("</svg>")

os.makedirs("profile", exist_ok=True)
with open("profile/stats.svg", "w", encoding="utf-8") as f:
    f.write("\n".join(parts))

print(f"Wrote profile/stats.svg ({H}px) for {name}")
print(f"  stars={total_stars} followers={followers} following={following} repos={public_repos} top={top_lang} commits={commits}")
