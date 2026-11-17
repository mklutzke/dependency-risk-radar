"""
EDA 01 - npm package universe and package -> GitHub repo mapping.

1. Pulls npm's "high-impact" package list (>= 1M weekly downloads OR >= 500
   dependents) from the npm-high-impact package on the public registry.
2. Fetches the latest manifest of each package from registry.npmjs.org.
3. Normalises the `repository` field to a GitHub owner/repo and reports:
   - match rate (how many packages point at a GitHub repo)
   - other hosts / missing / unparseable
   - monorepos (several packages -> one repo)
   - maintainer counts on npm (single-maintainer share)

Outputs (data/ is git-ignored):
  data/npm_packages.csv       one row per package
  data/npm_repo_summary.json  headline numbers for the deck

Usage:
  python eda/01_npm_package_universe.py            # all high-impact packages
  python eda/01_npm_package_universe.py --top 2000 # first N by downloads
"""
import argparse
import csv
import io
import json
import re
import tarfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

REGISTRY = "https://registry.npmjs.org"
HIGH_IMPACT_PKG = "npm-high-impact"
OUT = Path(__file__).resolve().parents[1] / "data"
OUT.mkdir(exist_ok=True)

GH_PATTERNS = [
    re.compile(r"github\.com[:/]+([^/\s#]+)/([^/\s#?]+)", re.I),
    re.compile(r"^github:([^/\s#]+)/([^/\s#?]+)$", re.I),
    re.compile(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$"),  # npm shorthand "user/repo"
]


def load_high_impact():
    """Return (ordered_names, by_download_rank, dependent_set, version)."""
    meta = requests.get(f"{REGISTRY}/{HIGH_IMPACT_PKG}/latest", timeout=30).json()
    tgz = requests.get(meta["dist"]["tarball"], timeout=60).content
    lists = {}
    with tarfile.open(fileobj=io.BytesIO(tgz)) as tf:
        for key in ("top", "top-download", "top-dependent"):
            src = tf.extractfile(f"package/lib/{key}.js").read().decode()
            lists[key] = re.findall(r"'([^']+)'", src)
    dl_rank = {n: i + 1 for i, n in enumerate(lists["top-download"])}
    return lists["top"], dl_rank, set(lists["top-dependent"]), meta["version"]


def parse_repo(repo):
    """Return (host, owner/repo or None, directory or None)."""
    if not repo:
        return "missing", None, None
    directory = None
    if isinstance(repo, dict):
        directory = repo.get("directory")
        url = repo.get("url") or ""
    else:
        url = str(repo)
    url = url.strip()
    if not url:
        return "missing", None, directory
    for host in ("gitlab", "bitbucket"):
        if host in url.lower():
            return host, None, directory
    for pat in GH_PATTERNS:
        m = pat.search(url)
        if m:
            owner, name = m.group(1), m.group(2)
            name = re.sub(r"\.git$", "", name)
            return "github", f"{owner}/{name}".lower(), directory
    return "other", None, directory


def fetch(name):
    url = f"{REGISTRY}/{name.replace('/', '%2F')}/latest"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            return {"package": name, "status": r.status_code}
        j = r.json()
    except Exception as e:  # network hiccup, bad JSON
        return {"package": name, "status": f"error: {type(e).__name__}"}
    host, gh, directory = parse_repo(j.get("repository"))
    return {
        "package": name,
        "status": 200,
        "version": j.get("version"),
        "deprecated": bool(j.get("deprecated")),
        "repo_host": host,
        "github_repo": gh,
        "repo_directory": directory,
        "n_maintainers": len(j.get("maintainers") or []),
        "publisher": (j.get("_npmUser") or {}).get("name"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=None, help="limit to first N packages")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--budget", type=int, default=None,
                    help="stop fetching after N seconds; rerun to resume from cache")
    args = ap.parse_args()

    names, dl_rank, dependents, hi_version = load_high_impact()
    if args.top:
        names = names[: args.top]
    print(f"npm-high-impact {hi_version}: {len(names):,} packages")

    # Resumable: every manifest we fetch is appended to a JSONL cache.
    cache_path = OUT / "npm_latest_cache.jsonl"
    cache = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["status"] == 200:
                cache[r["package"]] = r
    todo = [n for n in names if n not in cache]
    print(f"  cached: {len(cache):,}  to fetch: {len(todo):,}")

    start = time.time()
    with ThreadPoolExecutor(args.workers) as ex, open(cache_path, "a", encoding="utf-8") as fh:
        for b in range(0, len(todo), 1000):
            if args.budget and time.time() - start > args.budget:
                print("  budget reached - rerun to resume")
                return
            for r in ex.map(fetch, todo[b:b + 1000]):
                cache[r["package"]] = r
                fh.write(json.dumps(r) + "\n")
            fh.flush()
            print(f"  {min(b + 1000, len(todo)):,}/{len(todo):,}")
    rows = [dict(cache[n]) for n in names if n in cache]

    for r in rows:
        r["download_rank"] = dl_rank.get(r["package"])
        r["high_dependents"] = r["package"] in dependents
        r["scoped"] = r["package"].startswith("@")

    ok = [r for r in rows if r["status"] == 200]
    gh = [r for r in ok if r["repo_host"] == "github"]
    pkgs_per_repo = Counter(r["github_repo"] for r in gh)
    for r in gh:
        r["pkgs_in_repo"] = pkgs_per_repo[r["github_repo"]]
    mono_repos = {k for k, v in pkgs_per_repo.items() if v > 1}

    fields = ["package", "status", "version", "deprecated", "repo_host", "github_repo",
              "repo_directory", "pkgs_in_repo", "n_maintainers", "publisher",
              "download_rank", "high_dependents", "scoped"]
    rows.sort(key=lambda r: (r["download_rank"] or 10**9, r["package"]))
    with open(OUT / "npm_packages.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    hosts = Counter(r["repo_host"] for r in ok)
    maint = Counter(min(r["n_maintainers"], 5) for r in ok)
    summary = {
        "high_impact_version": hi_version,
        "packages_requested": len(names),
        "packages_fetched": len(ok),
        "fetch_failures": len(rows) - len(ok),
        "repo_host_counts": dict(hosts),
        "github_match_rate": round(len(gh) / len(ok), 4),
        "distinct_github_repos": len(pkgs_per_repo),
        "monorepos_(repos_with_>1_pkg)": len(mono_repos),
        "packages_in_monorepos": sum(pkgs_per_repo[k] for k in mono_repos),
        "packages_per_repo_max": pkgs_per_repo.most_common(10),
        "deprecated_share": round(sum(r["deprecated"] for r in ok) / len(ok), 4),
        "maintainers_hist_(5=5+)": dict(sorted(maint.items())),
        "single_maintainer_share": round(maint.get(1, 0) / len(ok), 4),
        "scoped_share": round(sum(r["scoped"] for r in ok) / len(ok), 4),
    }
    (OUT / "npm_repo_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
