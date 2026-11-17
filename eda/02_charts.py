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
#    Flags every day as ok / partial / missing and writes data/gha_day_flags.csv
#    (feeds the coverage flag in dim_month). The last 2 days are dropped:
#    GH Archive lags a few hours, so they are still filling in.
if p := need("gha_day_tables.csv"):
    d = pd.read_csv(p, parse_dates=["day"]).sort_values("day").iloc[:-2]
    full = pd.date_range(d.day.min(), d.day.max(), name="day")
    s = d.set_index("day").events.reindex(full)
    med = s.rolling(29, center=True, min_periods=10).median()
    flags = pd.DataFrame({"events": s, "median_29d": med})
    flags["ratio"] = flags.events / flags.median_29d
    flags["status"] = "ok"
    flags.loc[flags.ratio < 0.5, "status"] = "partial"      # under half of a normal day
    flags.loc[flags.events.isna(), "status"] = "missing"    # no table at all
    flags.to_csv(DATA / "gha_day_flags.csv")
    miss, part = flags[flags.status == "missing"], flags[flags.status == "partial"]
    recent = part[part.index >= "2025-01-01"]
    print(f"coverage: {len(flags):,} days, {len(miss)} missing, {len(part)} partial "
          f"({len(recent)} of them since 2025)")

    with plt.rc_context({"font.size": 14}):
        fig, ax = plt.subplots(figsize=(9.4, 3.85))
        ax.plot(s.index, s / 1e6, color=GREY, lw=0.5, alpha=0.7, label="daily")
        ax.plot(med.index, med / 1e6, color=MAROON, lw=2, label="29-day median")
        ax.scatter(part.index, part.events / 1e6, s=18, color="#B7791F", zorder=3,
                   label=f"partial day (<50% of median): {len(part)}")
        ax.scatter(miss.index, [0] * len(miss), marker="|", s=250, color="#B7791F",
                   linewidths=2, zorder=3, label=f"missing day: {len(miss)}")
        ax.set_ylabel("events per day (M)")
        ax.set_ylim(0, med.max() / 1e6 * 1.45)
        ax.legend(frameon=False, loc="upper left", fontsize=11)
        fig.suptitle("GH Archive events per day (BigQuery day tables)", x=0.01, ha="left",
                     fontsize=14, color=DARK)
        save(fig, "gha_events_per_day.png")

# 4) GH Archive size per year ------------------------------------------------
if p := need("gha_year_tables.csv"):
    y = pd.read_csv(p).sort_values("year")
    y["kb_per_event"] = y.gib_logical * 1024**3 / y.events / 1024
    y["yoy"] = y.events.pct_change()
    last = y.iloc[-1]
    first_drop = (y.yoy.iloc[1:-1] >= 0).all() and last.yoy < 0
    with plt.rc_context({"font.size": 14}):
        fig, (a1, a2) = plt.subplots(2, 1, figsize=(9.4, 3.84), sharex=True,
                                     gridspec_kw={"height_ratios": [1.7, 1]})
        yrs = y.year.astype(str)
        a1.bar(yrs, y.events / 1e9, width=0.7,
               color=[MAROON if yy < last.year else "#B7791F" for yy in y.year])
        for x, v in zip(yrs, y.events / 1e9):
            a1.text(x, v, f"{v:.2f}", ha="center", va="bottom", fontsize=11)
        a1.set_ylabel("events (B)")
        a1.set_ylim(0, y.events.max() / 1e9 * 1.3)
        note = f"{last.yoy:+.0%} vs {int(last.year) - 1}" + (": first yearly drop" if first_drop else "")
        a1.annotate(note, xy=(len(y) - 1, last.events / 1e9 + 0.12), xytext=(len(y) - 0.65, y.events.max() / 1e9 * 1.18),
                    fontsize=12, color="#B7791F", ha="right",
                    arrowprops=dict(arrowstyle="-", color="#B7791F"))
        a2.plot(yrs, y.kb_per_event, marker="o", color="#5B6770")
        a2.set_ylabel("KB / event")
        a2.set_ylim(0, y.kb_per_event.max() * 1.3)
        fig.suptitle("GH Archive events per year, and average stored size per event (BigQuery)",
                     x=0.01, ha="left", fontsize=14, color=DARK)
        save(fig, "gha_events_per_year.png")

# 5) Event-type mix on sample days -----------------------------------------
if p := need("gha_type_mix_sample_days.csv"):
    t = pd.read_csv(p, dtype={"day": str})
    t["year"] = t.day.str[:4]
    keep = ["PushEvent", "PullRequestEvent", "IssuesEvent", "IssueCommentEvent",
            "WatchEvent", "CreateEvent", "ReleaseEvent", "MemberEvent"]
    t["type2"] = t.type.where(t.type.isin(keep), "Other")
    piv = t.pivot_table(index="year", columns="type2", values="events", aggfunc="sum").fillna(0)
    share = piv.div(piv.sum(axis=1), axis=0)
    # control types in maroon/slate, issue activity in amber, the rest grey
    colors = {"PushEvent": MAROON, "PullRequestEvent": "#C9A3A3", "CreateEvent": "#5B6770",
              "ReleaseEvent": "#2B2B2B", "MemberEvent": "#000000",
              "IssuesEvent": "#B7791F", "IssueCommentEvent": "#E2B865",
              "WatchEvent": "#D9D9D9", "Other": GREY}
    order = [c for c in colors if c in share.columns]
    with plt.rc_context({"font.size": 14}):
        fig, ax = plt.subplots(figsize=(8.2, 4.6))
        share[order].plot(kind="bar", stacked=True, ax=ax, width=0.8,
                          color=[colors[c] for c in order])
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
        ax.set_xlabel("")
        ax.tick_params(axis="x", rotation=0, labelsize=11)
        h, l = ax.get_legend_handles_labels()
        ax.legend(h[::-1], [c.replace("Event", "") for c in l][::-1],
                  bbox_to_anchor=(1.01, 1), loc="upper left", frameon=False, fontsize=11)
        ax.set_title("Event-type mix, one mid-June Wednesday per year", loc="left", fontsize=14)
        save(fig, "gha_type_mix.png")

        bots = t.groupby("year")[["bot_events", "events"]].sum()
        fig, ax = plt.subplots(figsize=(5.2, 4.6))
        ax.plot(bots.index, bots.bot_events / bots.events, marker="o", color=MAROON)
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
        ax.set_xticks(bots.index[::2])
        ax.tick_params(axis="x", labelsize=11)
        ax.set_title("Share of events from [bot] accounts", loc="left", fontsize=14)
        save(fig, "gha_bot_share.png")

# 6) event-stream: control events by actor vs everyone else, per month -------
#    All annotation numbers are computed from the CSV, not typed in.
if p := need("es_monthly_actor_type.csv"):
    e = pd.read_csv(p)
    e["first_seen"] = pd.to_datetime(e.first_seen.str.replace(" UTC", ""))
    months = sorted(e.month.unique())
    labels = [pd.Timestamp(m + "-01").strftime("%b") for m in months]
    CONTROL = ["PushEvent", "ReleaseEvent", "MemberEvent", "CreateEvent", "DeleteEvent"]
    ctrl = e[e.type.isin(CONTROL)]
    piv = (ctrl.pivot_table(index="month", columns="actor", values="events", aggfunc="sum")
           .reindex(months).fillna(0))          # keep months with zero control events
    order = list(piv.sum().sort_values(ascending=False).index)
    rest = (e[~e.type.isin(CONTROL)].groupby("month")
            .agg(events=("events", "sum"), actors=("actor", "nunique"))
            .reindex(months).fillna(0))

    with plt.rc_context({"font.size": 14}):
        fig, (a1, a2) = plt.subplots(2, 1, figsize=(8.6, 3.93), sharex=True,
                                     gridspec_kw={"height_ratios": [1.25, 1]})
        bottom = pd.Series(0.0, index=months)
        palette = [MAROON, "#5B6770", GREY, "#C8A2A2"]
        for i, actor in enumerate(order[:4]):
            a1.bar(labels, piv[actor].values, bottom=bottom.values,
                   color=palette[i], label=actor, width=0.7)
            bottom += piv[actor]
        a1.set_ylabel("control\nevents")
        a1.legend(frameon=False, loc="upper left", fontsize=12)
        peak = piv.sum(axis=1).idxmax()
        top_actor = piv.loc[peak].idxmax()
        n_top, n_tot = int(piv.loc[peak, top_actor]), int(piv.loc[peak].sum())
        first = e[e.actor == top_actor].first_seen.min()
        quiet = int((piv.sum(axis=1).loc[:peak] == 0).sum())
        pi = months.index(peak)
        a1.annotate(f"{top_actor}: {n_top} of {n_tot} control events\nfirst seen on the repo {first:%b} {first.day}",
                    xy=(pi, n_tot), xytext=(pi + 0.6, n_tot * 0.75), fontsize=12,
                    color=MAROON, arrowprops=dict(arrowstyle="-", color=MAROON))
        a1.text((pi - 1) / 2, n_tot * 0.3, f"{quiet} months with no control events",
                ha="center", fontsize=12, color=DARK)
        a1.set_ylim(0, n_tot * 1.25)

        a2.bar(labels, rest.events.values, color=GREY, width=0.7)
        spike = rest.events.idxmax()
        si = months.index(spike)
        a2.annotate(f"{int(rest.loc[spike, 'events']):,} events from\n{int(rest.loc[spike, 'actors']):,} accounts (discovery)",
                    xy=(si, rest.loc[spike, "events"]), xytext=(si - 3.6, rest.events.max() * 0.45),
                    fontsize=12, arrowprops=dict(arrowstyle="-", color=DARK))
        a2.set_ylabel("everyone\nelse")
        fig.suptitle("dominictarr/event-stream, 2018 (GH Archive)", x=0.01, ha="left",
                     fontsize=14, color=DARK)
        save(fig, "event_stream_control.png")

# summary numbers, if present
if p := need("npm_repo_summary.json"):
    s = json.loads(p.read_text())
    print("npm summary:", {k: s[k] for k in ("packages_fetched", "github_match_rate",
                                              "single_maintainer_share")})
