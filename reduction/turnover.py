"""Trigger-time and period-label calculations for a Site's Beat schedule.

See "Reduction period turnover" in specs/plans/pyobs-pipeline.md (pyobs-core repo) for
the reasoning: trigger time (when Beat fires) and period label (which calendar date a
frame belongs to) are computed separately, from opposite reference points.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import astropy.units as u
from astroplan import Observer
from astropy.time import Time

from reduction.models import Site


def _observer(site: Site) -> Observer:
    return Observer(latitude=site.lat * u.deg, longitude=site.lon * u.deg, timezone=site.timezone)


def get_next_turnover(site: Site, now: dt.datetime | None = None) -> dt.datetime:
    """Next Beat trigger time for a site, as a UTC-aware datetime."""
    now = now or dt.datetime.now(dt.timezone.utc)

    if site.trigger_type == "fixed_time":
        tz = ZoneInfo(site.timezone)
        local_now = now.astimezone(tz)
        trigger_local = dt.datetime.combine(local_now.date(), site.trigger_time, tzinfo=tz)
        if trigger_local <= local_now:
            trigger_local += dt.timedelta(days=1)
        return trigger_local.astimezone(dt.timezone.utc)

    event = "rise" if site.trigger_type == "sunrise" else "set"
    t = getattr(_observer(site), f"sun_{event}_time")(Time(now), which="next")
    return t.to_datetime(timezone=dt.timezone.utc) + dt.timedelta(hours=site.delay_hours)


def get_period_label(site: Site, at: dt.datetime | None = None) -> dt.date:
    """The ReductionPeriod.date a trigger at `at` belongs to: the local calendar date of
    the most recent occurrence of the *opposite* reference point before `at`."""
    at = at or dt.datetime.now(dt.timezone.utc)
    tz = ZoneInfo(site.timezone)

    if site.trigger_type == "fixed_time":
        local_at = at.astimezone(tz)
        trigger_local = dt.datetime.combine(local_at.date(), site.trigger_time, tzinfo=tz)
        if trigger_local > local_at:
            trigger_local -= dt.timedelta(days=1)
        return trigger_local.date()

    # sunrise trigger -> most recent sunset; sunset trigger -> most recent sunrise
    opposite = "set" if site.trigger_type == "sunrise" else "rise"
    t = getattr(_observer(site), f"sun_{opposite}_time")(Time(at), which="previous")
    return t.to_datetime(timezone=tz).date()


def get_missing_period_dates(
    site: Site, since: dt.date | None, max_days: int, now: dt.datetime | None = None
) -> list[dt.date]:
    """Period-label dates for every trigger instant that has already occurred, after
    `since` (exclusive) and within the last `max_days` -- see MAX_BACKFILL_DAYS in
    settings.py.

    `since` is the date of the site's last known ReductionPeriod, or None if it has
    never had one.

    Deliberately walks forward through actual trigger instants via `get_next_turnover`
    rather than comparing calendar dates: `get_period_label(site, now)` only changes at
    the *opposite* reference crossing (e.g. sunset for a sunrise-triggered site), not at
    the trigger instant itself (sunrise + delay_hours) -- so for several hours after a
    trigger has actually fired, a same-day label-based comparison would still think it
    hadn't (confirmed empirically: for a sunrise site, get_period_label(now) doesn't
    advance until evening, well after the morning trigger already ran).
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    # +1 day margin: a walk starting exactly `max_days` back can land mid-cycle and miss
    # the trigger that opens the window, undershooting the cap by one. Overshooting by
    # at most one extra day is the safer failure mode for a cap that exists to bound a
    # backlog, not hit an exact count.
    cursor = now - dt.timedelta(days=max_days + 1)

    labels: list[dt.date] = []
    for _ in range(max_days + 2):  # one trigger/day at most -- safety cap on iterations
        trigger_at = get_next_turnover(site, now=cursor)
        if trigger_at > now:
            break
        cursor = trigger_at
        label = get_period_label(site, at=trigger_at)
        if since is not None and label <= since:
            continue
        if label not in labels:
            labels.append(label)
    return labels
