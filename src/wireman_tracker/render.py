from __future__ import annotations

import json
from html import escape

from wireman_tracker.models import JobLead, SourceReport


def _badge(label: str, tone: str) -> str:
    tone_map = {
        "priority": "bg-amber-300/90 text-slate-950 ring-1 ring-amber-100/30",
        "watch": "bg-cyan-300/16 text-cyan-100 ring-1 ring-cyan-300/22",
        "expired": "bg-slate-800 text-slate-300 ring-1 ring-white/8",
        "source": "bg-white/8 text-slate-100 ring-1 ring-white/10",
        "hub": "bg-emerald-300/16 text-emerald-100 ring-1 ring-emerald-300/22",
        "regional": "bg-sky-300/14 text-sky-100 ring-1 ring-sky-300/22",
        "warn": "bg-orange-300/16 text-orange-100 ring-1 ring-orange-300/22",
        "relocation": "bg-fuchsia-300/14 text-fuchsia-100 ring-1 ring-fuchsia-300/24",
    }
    classes = tone_map.get(tone, "bg-white/8 text-slate-100 ring-1 ring-white/10")
    return (
        f'<span class="inline-flex rounded-full px-3 py-1 text-xs font-semibold tracking-[0.04em] '
        f'{classes}">{escape(label)}</span>'
    )


def _job_card(job: JobLead) -> str:
    description_text = job.description[:420] + ("..." if len(job.description) > 420 else "")
    description = escape(description_text or "Description not captured for this listing yet.")
    reasons = "".join(_badge(reason, "watch") for reason in job.reasons[:4])
    hubs = "".join(_badge(hub, "hub") for hub in job.hub_matches)
    regional = "".join(
        _badge(f"Regional fit: {match}", "regional")
        for match in job.metadata.get("regional_matches", [])[:2]
    )
    score_badge = _badge(f"Score {job.score}", "priority" if job.bucket == "priority" else "watch")
    status_badge = _badge(
        "New today" if job.first_seen == job.last_seen else "Seen before",
        "priority" if job.first_seen == job.last_seen else "source",
    )
    relocation_badge = (
        _badge("Relocation help mentioned", "relocation")
        if job.metadata.get("relocation_assistance")
        else ""
    )

    meta_bits = [job.company, job.location, job.posted_date, job.source_name]
    meta = " | ".join(escape(bit) for bit in meta_bits if bit)

    return f"""
    <article class="rounded-[1.8rem] border border-white/10 bg-slate-950/78 p-5 shadow-[0_22px_70px_rgba(2,6,23,0.45)] backdrop-blur lg:p-6">
      <div class="mb-3 flex flex-wrap items-center gap-2">
        {score_badge}
        {status_badge}
        {_badge(job.source_name, "source")}
        {hubs}
        {regional}
        {relocation_badge}
      </div>
      <h3 class="text-xl font-bold text-white lg:text-2xl">
        <a class="decoration-cyan-300 underline-offset-4 hover:text-cyan-100 hover:underline" href="{escape(job.detail_url)}">{escape(job.title)}</a>
      </h3>
      <p class="mt-2 text-sm uppercase tracking-[0.22em] text-slate-400">{meta}</p>
      <p class="mt-4 text-sm leading-7 text-slate-200 lg:text-base">{description}</p>
      <div class="mt-5 flex flex-wrap gap-2">{reasons}</div>
      <div class="mt-5 flex items-center justify-between border-t border-white/8 pt-4">
        <p class="text-xs uppercase tracking-[0.22em] text-slate-500">Daily tracked lead</p>
        <a class="text-sm font-semibold text-cyan-200 hover:text-white" href="{escape(job.detail_url)}">Open listing</a>
      </div>
    </article>
    """


def _source_card(report: SourceReport) -> str:
    tone = "source"
    if report.status == "warning":
        tone = "warn"
    elif report.status == "error":
        tone = "expired"

    notes = report.notes + report.errors
    notes_html = "".join(
        f"<li class='text-sm leading-6 text-slate-300'>{escape(note)}</li>" for note in notes
    ) or "<li class='text-sm leading-6 text-slate-500'>No extra notes.</li>"

    browser_note = _badge("Browser fallback", "watch") if report.used_browser else ""

    return f"""
    <article class="rounded-[1.6rem] border border-white/10 bg-slate-950/72 p-5">
      <div class="mb-3 flex flex-wrap items-center gap-2">
        {_badge(report.status.title(), tone)}
        {browser_note}
      </div>
      <h3 class="text-xl font-bold text-white">{escape(report.source_name)}</h3>
      <p class="mt-2 text-sm text-slate-300">
        Fetched {report.total_fetched} listings | Relevant leads {report.total_relevant}
      </p>
      <ul class="mt-4 space-y-2">{notes_html}</ul>
    </article>
    """


def render_index(generated_at: str, jobs: list[JobLead], reports: list[SourceReport]) -> str:
    active = [job for job in jobs if job.status == "active"]
    relevant_active = [job for job in active if job.bucket in {"priority", "watch"}]
    priority_jobs = [job for job in relevant_active if job.bucket == "priority"]
    watch_jobs = [job for job in relevant_active if job.bucket == "watch"]
    west_coast_watch = [
        job for job in watch_jobs if job.metadata.get("regional_matches")
    ]
    national_watch = [
        job for job in watch_jobs if not job.metadata.get("regional_matches")
    ]
    expired = [
        job
        for job in jobs
        if job.status == "expired" and job.bucket in {"priority", "watch"}
    ]

    total_active = len(relevant_active)
    total_new = len([job for job in relevant_active if job.first_seen == job.last_seen])
    relocation_count = len(
        [job for job in relevant_active if job.metadata.get("relocation_assistance")]
    )
    regional_count = len(
        [job for job in relevant_active if job.metadata.get("regional_matches")]
    )
    national_count = len(national_watch)
    source_health = "".join(_source_card(report) for report in reports)
    priority_html = "".join(_job_card(job) for job in priority_jobs) or (
        "<p class='rounded-[1.8rem] border border-dashed border-white/12 bg-slate-950/60 p-6 text-slate-300'>"
        "No priority leads are live from this scrape yet. The watchlist below still includes worthwhile nearby or adjacent opportunities."
        "</p>"
    )
    west_coast_html = "".join(_job_card(job) for job in west_coast_watch) or (
        "<p class='rounded-[1.8rem] border border-dashed border-cyan-400/20 bg-slate-950/60 p-6 text-slate-300'>"
        "No Oregon, Pacific Northwest, or California leads cleared the watch threshold in this scrape. The broader national list remains active below so the pipeline never goes dark."
        "</p>"
    )
    national_html = "".join(_job_card(job) for job in national_watch) or (
        "<p class='rounded-[1.8rem] border border-dashed border-white/12 bg-slate-950/60 p-6 text-slate-300'>"
        "No broader national watchlist leads met the current threshold."
        "</p>"
    )
    expired_html = "".join(_job_card(job) for job in expired[:12]) or (
        "<p class='rounded-[1.8rem] border border-dashed border-white/12 bg-slate-950/60 p-6 text-slate-300'>"
        "Nothing relevant has dropped off recently."
        "</p>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Wireman Tracker</title>
    <meta
      name="description"
      content="Daily apprentice electrician and inside wireman lead tracker with a bias toward data center and mission critical work."
    />
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Space+Grotesk:wght@400;500;700&display=swap" rel="stylesheet" />
    <script>
      tailwind.config = {{
        theme: {{
          extend: {{
            fontFamily: {{
              sans: ['Space Grotesk', 'ui-sans-serif', 'sans-serif'],
              serif: ['Instrument Serif', 'Georgia', 'serif']
            }}
          }}
        }}
      }}
    </script>
  </head>
  <body class="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.16),_transparent_26%),radial-gradient(circle_at_82%_18%,_rgba(251,191,36,0.14),_transparent_20%),linear-gradient(180deg,#020617_0%,#0f172a_40%,#111827_100%)] text-slate-100">
    <main class="mx-auto max-w-7xl px-6 py-10 lg:px-10">
      <section class="overflow-hidden rounded-[2.2rem] border border-white/10 bg-slate-950/82 text-white shadow-[0_30px_100px_rgba(2,6,23,0.55)] backdrop-blur">
        <div class="grid gap-8 px-8 py-10 lg:grid-cols-[1.4fr_0.8fr] lg:px-12 lg:py-14">
          <div>
            <p class="text-sm uppercase tracking-[0.35em] text-cyan-200">Donovan's Live Wire</p>
            <h1 class="mt-4 max-w-3xl text-4xl font-bold leading-[0.95] text-white lg:text-6xl">
              Daily apprentice electrician leads with an Oregon-first lens.
            </h1>
            <p class="mt-6 max-w-2xl text-base leading-8 text-slate-300 lg:text-lg">
              Priority leads stay at the top, West Coast and nearby options get their own lane, and the broader national market stays visible underneath so relocation-worthy openings never disappear from view.
            </p>
            <div class="mt-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <div class="rounded-2xl border border-white/10 bg-white/6 p-4">
                <p class="text-xs uppercase tracking-[0.22em] text-slate-400">Active Leads</p>
                <p class="mt-2 text-3xl font-bold text-white">{total_active}</p>
              </div>
              <div class="rounded-2xl border border-amber-200/10 bg-amber-300/8 p-4">
                <p class="text-xs uppercase tracking-[0.22em] text-amber-100/80">Priority</p>
                <p class="mt-2 text-3xl font-bold text-white">{len(priority_jobs)}</p>
              </div>
              <div class="rounded-2xl border border-sky-200/10 bg-sky-300/8 p-4">
                <p class="text-xs uppercase tracking-[0.22em] text-sky-100/80">West Coast Lane</p>
                <p class="mt-2 text-3xl font-bold text-white">{regional_count}</p>
              </div>
              <div class="rounded-2xl border border-white/10 bg-white/6 p-4">
                <p class="text-xs uppercase tracking-[0.22em] text-slate-400">National Lane</p>
                <p class="mt-2 text-3xl font-bold text-white">{national_count}</p>
              </div>
            </div>
            <div class="mt-6 flex flex-wrap gap-3">
              {_badge(f"{total_new} new today", "hub")}
              {_badge(f"{relocation_count} mention relocation", "relocation")}
              <a class="inline-flex rounded-full border border-white/12 px-4 py-2 text-sm font-semibold text-slate-200 hover:border-cyan-300/40 hover:text-white" href="#priority-leads">Jump to priority</a>
              <a class="inline-flex rounded-full border border-white/12 px-4 py-2 text-sm font-semibold text-slate-200 hover:border-cyan-300/40 hover:text-white" href="#west-coast-lane">Jump to West Coast</a>
              <a class="inline-flex rounded-full border border-white/12 px-4 py-2 text-sm font-semibold text-slate-200 hover:border-cyan-300/40 hover:text-white" href="#national-watchlist">Jump to national</a>
            </div>
          </div>
          <div class="rounded-[1.75rem] bg-white/6 p-6 ring-1 ring-white/10">
            <p class="text-sm uppercase tracking-[0.25em] text-slate-300">Latest Run</p>
            <p class="mt-3 text-3xl font-bold">{escape(generated_at)}</p>
            <p class="mt-4 text-sm leading-7 text-slate-300">
              Jobs can show as new, still active, or recently removed. Regional badges only appear when the role lands in Oregon, Washington, or California. Relocation badges appear only when a listing says that directly.
            </p>
            <p class="mt-6 text-sm text-slate-400">
              Static output: <code class="rounded bg-white/10 px-2 py-1 text-xs">docs/index.html</code>
            </p>
          </div>
        </div>
      </section>

      <section class="mt-10" id="priority-leads">
        <div class="mb-5">
          <p class="text-sm uppercase tracking-[0.28em] text-slate-400">Best Bets</p>
          <h2 class="mt-2 text-3xl font-bold text-white">Priority Leads</h2>
          <p class="mt-2 max-w-2xl text-sm leading-7 text-slate-400">
            Highest-signal openings with stronger apprentice alignment, stronger hub signals, or direct mission-critical context.
          </p>
        </div>
        <div class="grid gap-6">{priority_html}</div>
      </section>

      <section class="mt-12" id="west-coast-lane">
        <div class="mb-5">
          <p class="text-sm uppercase tracking-[0.28em] text-slate-400">Regional Lane</p>
          <h2 class="mt-2 text-3xl font-bold text-white">West Coast And Nearby</h2>
          <p class="mt-2 max-w-2xl text-sm leading-7 text-slate-400">
            Oregon, Washington, and California leads get surfaced here first so the local-to-relocatable path is easy to scan from a phone.
          </p>
        </div>
        <div class="grid gap-6 lg:grid-cols-2">{west_coast_html}</div>
      </section>

      <section class="mt-12" id="national-watchlist">
        <div class="mb-5">
          <p class="text-sm uppercase tracking-[0.28em] text-slate-400">Broader Net</p>
          <h2 class="mt-2 text-3xl font-bold text-white">National Watchlist</h2>
          <p class="mt-2 max-w-2xl text-sm leading-7 text-slate-400">
            This keeps Texas, Ohio, Mountain West, and other travel-ready openings in view without letting them bury the regional picture.
          </p>
        </div>
        <div class="grid gap-6 lg:grid-cols-2">{national_html}</div>
      </section>

      <section class="mt-12">
        <div class="mb-5">
          <p class="text-sm uppercase tracking-[0.28em] text-slate-400">Source Health</p>
          <h2 class="mt-2 text-3xl font-bold text-white">What Each Feed Produced</h2>
        </div>
        <div class="grid gap-5 md:grid-cols-2 xl:grid-cols-3">{source_health}</div>
      </section>

      <section class="mt-12">
        <div class="mb-5">
          <p class="text-sm uppercase tracking-[0.28em] text-slate-400">Recently Removed</p>
          <h2 class="mt-2 text-3xl font-bold text-white">No Longer Seen</h2>
        </div>
        <div class="grid gap-6 lg:grid-cols-2">{expired_html}</div>
      </section>
    </main>
  </body>
</html>
"""


def render_latest_json(generated_at: str, jobs: list[JobLead], reports: list[SourceReport]) -> str:
    active_jobs = [
        job.to_dict()
        for job in jobs
        if job.status == "active" and job.bucket in {"priority", "watch"}
    ]
    payload = {
        "generated_at": generated_at,
        "jobs": active_jobs,
        "reports": [report.to_dict() for report in reports],
    }
    return json.dumps(payload, indent=2)
