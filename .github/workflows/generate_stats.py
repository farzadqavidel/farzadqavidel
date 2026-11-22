import argparse
import datetime as dt
import html
import json
import os
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

API = "https://api.github.com"
UTC = dt.timezone.utc
SANS = "Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
MONO = "ui-monospace, DejaVu Sans Mono, Consolas, monospace"
LANG_COLORS = {
    "JavaScript": "#f1e05a", "TypeScript": "#83a8ff", "CSS": "#b9a0ff",
    "HTML": "#ee8b78", "Python": "#83b6e0", "C#": "#88ce9c",
    "Shell": "#7ce0bb", "Go": "#74d9ee", "Rust": "#daa78e",
}
ICONS = {
    "star": '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z"/>',
    "repo": '<path d="M5 18.5A2.5 2.5 0 0 1 7.5 16H20M7.5 3H20v18H7.5A2.5 2.5 0 0 1 5 18.5v-13A2.5 2.5 0 0 1 7.5 3Z"/><path d="M9 7h5"/>',
    "users": '<path d="M3 21v-2a5 5 0 0 1 5-5h3a5 5 0 0 1 5 5v2M18 14a5 5 0 0 1 3 5v2"/><circle cx="9.5" cy="6.5" r="3.5"/><path d="M17 3a3.5 3.5 0 0 1 0 7"/>',
    "user": '<circle cx="12" cy="6.5" r="3.5"/><path d="M4.5 21v-2a5 5 0 0 1 5-5h5a5 5 0 0 1 5 5v2"/>',
    "branch": '<circle cx="6" cy="5" r="2.3"/><circle cx="6" cy="19" r="2.3"/><circle cx="18" cy="5" r="2.3"/><path d="M6 7.3v9.4M18 7.3A10 10 0 0 1 8 17"/>',
}


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).scheme != "https":
            raise ValueError("Refusing a non-HTTPS redirect")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            old_host = urllib.parse.urlparse(req.full_url).netloc
            if urllib.parse.urlparse(newurl).netloc != old_host:
                redirected.remove_header("Authorization")
        return redirected


def request_json(url, token=None, body=None):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Only HTTPS API requests are supported")
    headers = {"Accept": "application/json", "User-Agent": "farzad-profile-cards"}
    if token and parsed.netloc == "api.github.com":
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.build_opener(SafeRedirect()).open(req, timeout=40) as response:
        return json.load(response)


def normalize_days(rows, start, end):
    by_date = {}
    for row in rows:
        date = dt.date.fromisoformat(row["date"])
        if not start <= date <= end:
            continue
        count = row.get("count", row.get("contributionCount"))
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"Invalid contribution count for {date}")
        if date in by_date:
            raise ValueError(f"Duplicate contribution date: {date}")
        by_date[date] = count
    days = []
    for offset in range((end - start).days + 1):
        date = start + dt.timedelta(days=offset)
        if date not in by_date:
            raise ValueError(f"Contribution data is incomplete: missing {date}")
        days.append({"date": date.isoformat(), "count": by_date[date]})
    return days


def fetch_contributions(username, token, now):
    end = now.date()
    start = end - dt.timedelta(days=364)
    if token:
        query = """query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              contributionCalendar {
                weeks { contributionDays { date contributionCount } }
              }
            }
          }
        }"""
        try:
            data = request_json(f"{API}/graphql", token, {
                "query": query,
                "variables": {
                    "login": username,
                    "from": f"{start}T00:00:00Z",
                    "to": now.isoformat().replace("+00:00", "Z"),
                },
            })
            calendar = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
            rows = [day for week in calendar["weeks"] for day in week["contributionDays"]]
            return normalize_days(rows, start, end), "GitHub GraphQL API"
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"GraphQL unavailable; trying public calendar: {type(exc).__name__}", file=sys.stderr)
    url = f"https://github-contributions-api.jogruber.de/v4/{username}?y=last"
    data = request_json(url)
    return normalize_days(data["contributions"], start, end), "github-contributions-api.jogruber.de"


def collect_data(username, token=None):
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", username):
        raise ValueError("Invalid GitHub username")
    now = dt.datetime.now(UTC).replace(microsecond=0)
    user = request_json(f"{API}/users/{username}", token)
    repos, page = [], 1
    while True:
        chunk = request_json(f"{API}/users/{username}/repos?type=owner&per_page=100&page={page}", token)
        repos.extend(repo for repo in chunk if not repo.get("private"))
        if len(chunk) < 100:
            break
        page += 1
    languages = {}
    originals = [repo for repo in repos if not repo.get("fork")]
    for repo in originals:
        url = f"{API}/repos/{username}/{urllib.parse.quote(repo['name'], safe='')}/languages"
        for language, count in request_json(url, token).items():
            languages[language] = languages.get(language, 0) + count
    days, source = fetch_contributions(username, token, now)
    return {
        "schema_version": 1,
        "username": user["login"],
        "name": user.get("name") or user["login"],
        "updated_at": now.isoformat().replace("+00:00", "Z"),
        "followers": user["followers"],
        "following": user["following"],
        "public_repos": user["public_repos"],
        "stars": sum(repo.get("stargazers_count", 0) for repo in originals),
        "languages": dict(sorted(languages.items(), key=lambda pair: (-pair[1], pair[0]))),
        "contributions": days,
        "sources": {"profile": API, "contributions": source},
    }


def esc(value):
    return html.escape(str(value), quote=True)


def text(x, y, value, size=18, color="#8e9fb6", weight=400, mono=False, extra=""):
    family = MONO if mono else SANS
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}" {extra}>{esc(value)}</text>')


def icon(key, x, y, color="#8fe8cc", size=22):
    return (f'<g transform="translate({x} {y}) scale({size / 24:.5f})" fill="none" '
            f'stroke="{color}" stroke-width="1.7" stroke-linecap="round" '
            f'stroke-linejoin="round">{ICONS[key]}</g>')


def weekly_groups(days):
    return [days[index:index + 7] for index in range(0, len(days), 7)]


def render(data):
    days = data["contributions"]
    if len(days) != 365:
        raise ValueError("The card requires a complete 365-day calendar")
    start, end = (dt.date.fromisoformat(days[index]["date"]) for index in (0, -1))
    days = normalize_days(days, start, end)
    if len(days) != 365:
        raise ValueError("The calendar must cover exactly 365 consecutive days")
    total = sum(day["count"] for day in days)
    languages = sorted(data.get("languages", {}).items(), key=lambda pair: (-pair[1], pair[0]))
    top_language, top_bytes = languages[0] if languages else ("Not available", 0)
    all_bytes = sum(count for _, count in languages)
    percentage = f"{top_bytes / all_bytes:.1%}" if all_bytes else "—"
    name = data["name"] if len(data["name"]) <= 29 else data["name"][:28] + "…"
    lang_color = LANG_COLORS.get(top_language, "#8fe8cc")
    p = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="402" viewBox="0 0 800 804" fill="none" role="img" aria-labelledby="stats-title stats-desc">',
        f'<title id="stats-title">{esc(data["name"])} — GitHub overview</title>',
        f'<desc id="stats-desc">{total:,} GitHub contributions from {start} through {end}; '
        f'{data["stars"]:,} stars, {data["public_repos"]:,} public repositories, '
        f'{data["followers"]:,} followers, {data["following"]:,} following. '
        f'Top language by bytes in owned, non-fork public repositories: {esc(top_language)}, {percentage}. '
        'Contributions include more than commits. Each bar represents up to seven days.</desc>',
        '<defs><linearGradient id="stats-bg" x1="0" y1="0" x2="800" y2="804" gradientUnits="userSpaceOnUse"><stop stop-color="#101b27"/><stop offset=".48" stop-color="#0c131e"/><stop offset="1" stop-color="#101421"/></linearGradient>',
        '<linearGradient id="stats-border" x1="0" y1="0" x2="800" y2="804" gradientUnits="userSpaceOnUse"><stop stop-color="#405967"/><stop offset=".4" stop-color="#26374b"/><stop offset="1" stop-color="#30344b"/></linearGradient>',
        '<linearGradient id="stats-bars" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#a7f3da"/><stop offset="1" stop-color="#54acac"/></linearGradient>',
        '<clipPath id="stats-language-clip"><rect x="116" y="806" width="620" height="4" rx="2"/></clipPath></defs>',
        '<rect x=".75" y=".75" width="798.5" height="802.5" rx="24" fill="url(#stats-bg)" stroke="url(#stats-border)" stroke-width="1.5"/>',
        '<path d="M1 56H799" stroke="#243143"/>',
    ]
    for x, color in [(29, "#ed8b8b"), (49, "#e7c68b"), (69, "#89c7a5")]:
        p.append(f'<circle cx="{x}" cy="29" r="5" fill="{color}"/>')
    p.extend([
        text(96, 34, "github / overview", 15, "#9baabe", mono=True),
        text(768, 34, "stats.svg", 13, "#65778f", mono=True, extra='text-anchor="end"'),
        '<g id="stats-body" transform="translate(0 -44)">',
        text(32, 153, name, 37, "#edf3fa", 650),
        text(33, 185, "@" + data["username"], 19, "#92a2b9", mono=True),
        '<rect x="661" y="124" width="107" height="37" rx="18.5" fill="#15232c" stroke="#2a464c"/>',
        icon("branch", 675, 133, "#8fe8cc", 18),
        text(704, 149, "main", 16, "#b6ded4", mono=True),
        '<rect x="32" y="216" width="736" height="224" rx="18" fill="#101d29" stroke="#283b4b"/>',
        text(56, 252, "CONTRIBUTIONS", 15, "#9fbdc5", 500, mono=True, extra='letter-spacing="1.8"'),
        text(744, 252, "LAST 365 DAYS", 13, "#83adad", mono=True, extra='text-anchor="end" letter-spacing="1"'),
        text(52, 344, f"{total:,}", 78 if len(f"{total:,}") <= 7 else 58, "#e1fff3", 600, extra='letter-spacing="-3"'),
        text(56, 376, "A year of building.", 18, "#a1b3c8"),
        text(56, 413, f"{start:%d %b %Y} — {end:%d %b %Y}".upper(), 12, "#8498ae", mono=True),
        '<path d="M389 378H744" stroke="#2b404e"/>',
    ])
    groups = weekly_groups(days)
    counts = [sum(day["count"] for day in group) for group in groups]
    maximum = max(counts) or 1
    step = 355 / len(groups)
    for index, (group, count) in enumerate(zip(groups, counts)):
        height = 3 if count == 0 else max(5, (count / maximum) ** .7 * 94)
        x = 389 + index * step
        fill = "#253b48" if count == 0 else "url(#stats-bars)"
        p.append(f'<rect x="{x:.2f}" y="{378 - height:.2f}" width="{step - 2.2:.2f}" '
                 f'height="{height:.2f}" rx="1.5" fill="{fill}">'
                 f'<title>{group[0]["date"]} to {group[-1]["date"]}: {count} contributions</title></rect>')
    p.extend([
        text(389, 405, start.strftime("%b '%y").upper(), 12, "#8098a8", mono=True),
        text(744, 405, end.strftime("%b '%y").upper(), 12, "#8098a8", mono=True, extra='text-anchor="end"'),
    ])
    metrics = [
        (32, 460, "star", "Stars earned", data["stars"], "#e8d59c"),
        (410, 460, "repo", "Public repos", data["public_repos"], "#b9a8f3"),
        (32, 594, "users", "Followers", data["followers"], "#93cfec"),
        (410, 594, "user", "Following", data["following"], "#91d9ba"),
    ]
    for x, y, key, label, value, color in metrics:
        p.extend([
            f'<rect x="{x}" y="{y}" width="358" height="114" rx="16" fill="#111b28" stroke="#273447"/>',
            icon(key, x + 22, y + 22, color),
            text(x + 58, y + 40, label, 19, "#aebdd0"),
            text(x + 22, y + 91, f"{value:,}", 38, "#eef5fc", 550),
            f'<path d="M{x + 310} {y + 88}h24" stroke="{color}" stroke-opacity=".5" stroke-width="2" stroke-linecap="round"/>',
        ])
    mark = "JS" if top_language == "JavaScript" else top_language[:2].upper()
    p.extend([
        '<rect x="32" y="728" width="736" height="102" rx="16" fill="#131c29" stroke="#2a3648"/>',
        f'<rect x="56" y="755" width="43" height="43" rx="10" fill="{lang_color}" fill-opacity=".12" stroke="{lang_color}" stroke-opacity=".3"/>',
        text(77.5, 783, mark, 18, lang_color, 600, mono=True, extra='text-anchor="middle"'),
        text(116, 757, "TOP LANGUAGE", 13, "#96a7be", mono=True, extra='letter-spacing="1.5"'),
        text(115, 791, top_language, 26, "#ebf0f7", 550),
        text(736, 786, percentage, 29, lang_color, 500, extra='text-anchor="end"'),
        '<rect x="116" y="806" width="620" height="4" rx="2" fill="#253245"/>',
        '<g clip-path="url(#stats-language-clip)">',
    ])
    offset = 116.0
    for language, count in languages:
        width = count / all_bytes * 620 if all_bytes else 0
        color = LANG_COLORS.get(language, "#8fa4b9")
        p.append(f'<rect x="{offset:.3f}" y="806" width="{width:.3f}" height="4" fill="{color}"><title>{esc(language)}: {count:,} bytes</title></rect>')
        offset += width
    p.extend([
        '</g>',
        '</g>',
        '</svg>',
    ])
    return "\n".join(p) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Generate a GitHub stats SVG")
    parser.add_argument("username", nargs="?", default=os.environ.get("USERNAME", "farzadqavidel"))
    parser.add_argument("--output", type=Path, default=Path("profile/stats.svg"))
    args = parser.parse_args()
    data = collect_data(args.username, os.environ.get("GITHUB_TOKEN"))
    svg = render(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")
    total = sum(day["count"] for day in data["contributions"])
    print(f"Wrote {args.output}: {total:,} contributions, {data['stars']} stars; source: {data['sources']['contributions']}")


if __name__ == "__main__":
    main()
