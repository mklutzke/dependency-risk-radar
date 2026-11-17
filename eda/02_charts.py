"""
EDA 02 - turn query outputs in data/ into PNG charts in docs/img/.

Each chart is skipped (with a message) if its CSV isn't there yet, so you
can run this after every query and drop the new PNGs into the deck.

  python eda/02_charts.py
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
IMG = ROOT / "docs" / "img"
IMG.mkdir(parents=True, exist_ok=True)

MAROON, GREY, DARK = "#800000", "#9AA0A6", "#333333"
plt.rcParams.update({
    "font.size": 12, "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": GREY, "axes.labelcolor": DARK, "xtick.color": DARK,
    "ytick.color": DARK, "figure.dpi": 150,
})


def need(name):
    p = DATA / name
    if not p.exists():
        print(f"skip: {name} not found")
        return None
    return p


def save(fig, name):
    fig.tight_layout()
    fig.savefig(IMG / name, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote docs/img/{name}")


# 1) npm maintainers per package ------------------------------------------
if p := need("npm_packages.csv"):
    df = pd.read_csv(p, dtype=str)
    ok = df[df.status == "200"].copy()
    ok["maint"] = pd.to_numeric(ok.n_maintainers, errors="coerce").clip(upper=5)
    h = ok.maint.value_counts().sort_index()
    labels = [("5+" if i == 5 else str(int(i))) for i in h.index]
    fig, ax = plt.subplots(figsize=(6.4, 4))
    colors = [MAROON if i == 1 else GREY for i in h.index]
    ax.bar(labels, h.values, color=colors)
    for x, v in zip(labels, h.values):
        ax.text(x, v, f"{v:,}", ha="center", va="bottom", fontsize=10)
    ax.set_xlabel("npm maintainers on latest release")
    ax.set_ylabel("packages")
    ax.set_title(f"{h.get(1, 0) / len(ok):.0%} of {len(ok):,} high-impact packages "
                 "have one maintainer", fontsize=12, loc="left")
    save(fig, "npm_maintainers.png")

    # 2) package -> repo mapping funnel
    hosts = ok.repo_host.value_counts()
    gh = ok[ok.repo_host == "github"]
    per_repo = gh.github_repo.value_counts()
    mono_pkgs = int(per_repo[per_repo > 1].sum())
    steps = [
        ("high-impact packages", len(df)),
        ("manifest fetched", len(ok)),
        ("repo field -> GitHub", int(hosts.get("github", 0))),
        ("distinct GitHub repos", int(per_repo.size)),
    ]
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    names, vals = zip(*steps)
    ax.barh(names[::-1], vals[::-1], color=[GREY, GREY, MAROON, MAROON][::-1])
    for y, v in enumerate(vals[::-1]):
        ax.text(v, y, f" {v:,}", va="center", fontsize=10)
    ax.set_xlabel("count")
    ax.set_title(f"{mono_pkgs:,} packages share a repo with another package (monorepos)",
                 fontsize=11, loc="left")
    save(fig, "npm_repo_funnel.png")

# 3) GH Archive events per day (coverage) -----------------------------------
if p := need("gha_day_tables.csv"):
    d = pd.read_csv(p, parse_dates=["day"]).sort_values("day")
    d["roll"] = d.events.rolling(28, min_periods=7).median()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(d.day, d.events / 1e6, color=GREY, lw=0.5, alpha=0.6, label="daily")
    ax.plot(d.day, d.roll / 1e6, color=MAROON, lw=2, label="28-day median")
    ax.axvspan(pd.Timestamp("2025-01-01"), d.day.max(), color=MAROON, alpha=0.06)
    ax.set_ylabel("events per day (millions)")
    ax.set_title("GH Archive events per day, 2015 onward (shaded: degraded capture)",
                 loc="left")
    ax.legend(frameon=False)
    save(fig, "gha_events_per_day.png")

# 4) GH Archive size per year ------------------------------------------------
if p := need("gha_year_tables.csv"):
    y = pd.read_csv(p)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(y.year.astype(str), y.events / 1e9, color=MAROON)
    ax.set_ylabel("events (billions)")
    ax.set_title("GH Archive events per year", loc="left")
    save(fig, "gha_events_per_year.png")

# 5) Event-type mix on sample days -----------------------------------------
if p := need("gha_type_mix_sample_days.csv"):
    t = pd.read_csv(p, dtype={"day": str})
    t["year"] = t.day.str[:4]
    keep = ["PushEvent", "PullRequestEvent", "IssuesEvent", "IssueCommentEvent",
            "WatchEvent", "CreateEvent", "ReleaseEvent", "MemberEvent"]
    t["type2"] = t.type.where(t.type.isin(keep), "Other")
    piv = t.pivot_table(index="year", columns="type2", values="events", aggfunc="sum")
    share = piv.div(piv.sum(axis=1), axis=0)
    fig, ax = plt.subplots(figsize=(10, 4.5))
    share.plot(kind="bar", stacked=True, ax=ax, colormap="tab20", width=0.85)
    ax.set_ylabel("share of events")
    ax.set_xlabel("")
    ax.legend(bbox_to_anchor=(1.01, 1), loc="upper left", frameon=False, fontsize=9)
    ax.set_title("Event-type mix, one mid-June Wednesday per year", loc="left")
    save(fig, "gha_type_mix.png")

    bots = t.groupby("year")[["bot_events", "events"]].sum()
    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.plot(bots.index, bots.bot_events / bots.events, marker="o", color=MAROON)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_title("Share of events from [bot] accounts", loc="left")
    save(fig, "gha_bot_share.png")

# 6) event-stream: monthly control events by actor --------------------------
if p := need("es_monthly_actor_type.csv"):
    e = pd.read_csv(p)
    ctrl = e[e.type.isin(["PushEvent", "ReleaseEvent", "MemberEvent",
                          "CreateEvent", "DeleteEvent"])]
    piv = ctrl.pivot_table(index="month", columns="actor", values="events",
                           aggfunc="sum").fillna(0)
    top = piv.sum().sort_values(ascending=False).index[:4]
    piv = piv[top].assign(other=piv.drop(columns=top).sum(axis=1))
    fig, ax = plt.subplots(figsize=(10, 4))
    piv.plot(kind="bar", stacked=True, ax=ax,
             color=[MAROON, GREY, "#C8A2A2", "#5B5B5B", "#DDDDDD"][: piv.shape[1]])
    ax.set_ylabel("control events (push, release, member, create/delete)")
    ax.set_xlabel("")
    ax.set_title("dominictarr/event-stream, 2018: who controls the repo each month",
                 loc="left")
    ax.legend(frameon=False)
    save(fig, "event_stream_control.png")

    issues = e[e.type.isin(["IssuesEvent", "IssueCommentEvent"])].groupby("month").events.sum()
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.bar(issues.index, issues.values, color=GREY)
    ax.set_title("event-stream issue activity, 2018 (discovery spike in Nov)", loc="left")
    save(fig, "event_stream_issues.png")

# summary numbers, if present
if p := need("npm_repo_summary.json"):
    s = json.loads(p.read_text())
    print("npm summary:", {k: s[k] for k in ("packages_fetched", "github_match_rate",
                                              "single_maintainer_share")})
