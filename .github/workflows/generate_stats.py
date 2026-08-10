import json
import os
import sys
import datetime
import urllib.request

USERNAME = os.environ.get("USERNAME") or (
    sys.argv[1] if len(sys.argv) > 1 else "farzadqavidel")
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
    cu = f"https://github-contributions-api.jogruber.de/v4/{USERNAME}?y=last"
    data = get(cu)
    contributions = data.get("contributions", [])
    commits = sum(c.get("count", 0) for c in contributions)
except Exception:
    commits = "N/A"

# ---- icons (Feather-style, 24x24 viewBox) ----
ICONS = {
    "star":      ('<path d="M12 2l2.9 6.1 6.6.9-4.8 4.7 1.2 6.6L12 17.8 6.1 20.3l1.2-6.6L2.5 9l6.6-.9z"/>', "fill"),
    "commit":    ('<circle cx="12" cy="12" r="4"/><line x1="2" y1="12" x2="8" y2="12"/><line x1="16" y1="12" x2="22" y2="12"/>', "stroke"),
    "followers": ('<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>', "stroke"),
    "following": ('<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>', "stroke"),
    "repo":      ('<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>', "stroke"),
    "code":      ('<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>', "stroke"),
}


def icon_svg(key, x, y, size, color):
    inner, mode = ICONS[key]
    if mode == "fill":
        style = f'fill="{color}" stroke="none"'
    else:
        style = f'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
    return (f'<svg x="{x}" y="{y}" width="{size}" height="{size}" viewBox="0 0 24 24" {style}>'
            f'{inner}</svg>')


# ---- rows: (icon, color, label, value) ----
rows = [
    ("star",      "#ff79c6", "Total Stars Earned", f"{total_stars:,}"),
    ("commit",    "#f1fa8c", "Total Commits",
     f"{commits:,}" if isinstance(commits, int) else commits),
    ("followers", "#8be9fd", "Followers", f"{followers:,}"),
    ("following", "#50fa7b", "Following", f"{following:,}"),
    ("repo",      "#bd93f9", "Public Repos", f"{public_repos:,}"),
    ("code",      "#ffb86c", "Top Language", esc(top_lang)),
]

# ---- svg layout ----
W = 495
row_h = 34
title_y = 40
start_y = 82
H = start_y + len(rows) * row_h + 16

parts = []
parts.append(
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" fill="none">')
parts.append(
    f'<rect x="0.5" y="0.5" rx="12" ry="12" width="{W-1}" height="{H-1}" fill="#282a36"/>')

# title
parts.append(
    f'<text x="26" y="{title_y}" font-family="Segoe UI, Ubuntu, Helvetica, Arial, sans-serif" '
    f'font-size="19" font-weight="700" fill="#f8f8f2">{esc(name)}\'s GitHub Stats</text>'
)

for i, (icon, color, label, value) in enumerate(rows):
    ry = start_y + i * row_h
    iy = ry - 13
    parts.append(icon_svg(icon, 26, iy, 18, color))
    parts.append(
        f'<text x="54" y="{ry}" font-family="Segoe UI, Ubuntu, Helvetica, Arial, sans-serif" '
        f'font-size="14" font-weight="500" fill="#f8f8f2">{esc(label)}</text>'
    )
    parts.append(
        f'<text x="{W-26}" y="{ry}" font-family="Segoe UI, Ubuntu, Helvetica, Arial, sans-serif" '
        f'font-size="14" font-weight="700" fill="#f8f8f2" text-anchor="end">{value}</text>'
    )

parts.append("</svg>")

os.makedirs("profile", exist_ok=True)
with open("profile/stats.svg", "w", encoding="utf-8") as f:
    f.write("\n".join(parts))

print(f"Wrote profile/stats.svg ({H}px) for {name}")
print(f"  stars={total_stars} followers={followers} following={following} repos={public_repos} top={top_lang} commits={commits}")
