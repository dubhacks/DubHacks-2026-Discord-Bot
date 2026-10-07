from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from shared import logger, db, EVENT_SOURCES, EVENT_TZ


def load_usernames(collection_name):
    """Return the set of lowercased Discord usernames stored in a collection."""
    if db is None:
        logger.error("MongoDB is not available")
        return set()

    try:
        docs = db[collection_name].find(
            {"discord_id": {"$exists": True, "$nin": [None, ""]}},
            {"discord_id": 1},
        )
        usernames = {str(doc["discord_id"]).strip().lower() for doc in docs}
        logger.info(f"Loaded {len(usernames)} usernames from '{collection_name}'")
        return usernames
    except Exception as e:
        logger.error(f"Error loading '{collection_name}' from MongoDB: {e}")
        return set()


def members_by_username(guild):
    """Map lowercased username and display name to member, for fast lookup."""
    lookup = {}
    for member in guild.members:
        if member.bot:
            continue
        lookup.setdefault(member.display_name.lower(), member)
        lookup[member.name.lower()] = member  # real username wins over nicknames
    return lookup


def _as_utc(value):
    """pymongo returns naive datetimes in UTC; make them timezone-aware."""
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def load_events():
    """Return all workshops and activities, sorted by start time."""
    if db is None:
        logger.error("MongoDB is not available")
        return []

    events = []
    for collection_name, kind in EVENT_SOURCES.items():
        try:
            for doc in db[collection_name].find({}):
                events.append({
                    "kind": kind,
                    "name": doc.get("name") or "(unnamed)",
                    "start": _as_utc(doc.get("start")),
                    "end": _as_utc(doc.get("end")),
                    "location": doc.get("location") or "TBD",
                    "reward": doc.get("dubcoinReward") or 0,
                })
        except Exception as e:
            logger.error(f"Error loading '{collection_name}' from MongoDB: {e}")

    far_future = datetime.max.replace(tzinfo=timezone.utc)
    events.sort(key=lambda ev: (ev["start"] or far_future, ev["name"]))
    logger.info(f"Loaded {len(events)} events")
    return events


def _fmt_time(dt):
    return dt.strftime("%I:%M %p")


NAME_WIDTH = 26   # characters before an event name is clipped
TIME_WIDTH = 8    # "10:00 AM"


def _clip(text, width):
    text = str(text)
    return text if len(text) <= width else text[: width - 1] + "…"


def _table(rows):
    """Render (time, name, location) rows as an aligned monospace block."""
    lines = [
        f"{time:>{TIME_WIDTH}}  {_clip(name, NAME_WIDTH):<{NAME_WIDTH}}  {location}".rstrip()
        for time, name, location in rows
    ]
    return "```\n" + "\n".join(lines) + "\n```"


def format_schedule(events):
    """Group events by day, workshops and activities merged chronologically.

    Returns a list of (day_title, code_block_text) pairs. `events` is
    expected to be sorted by start time already (load_events does this).
    """
    tz = ZoneInfo(EVENT_TZ)
    by_day = {}  # (date, title) -> [(time, name, location), ...]
    for ev in events:
        start = ev["start"].astimezone(tz) if ev["start"] else None
        day_key = start.date() if start else None
        day_title = start.strftime("%A, %B %d") if start else "Unscheduled"
        when = _fmt_time(start) if start else "TBD"
        by_day.setdefault((day_key, day_title), []).append((when, ev["name"], ev["location"]))

    ordered = sorted(by_day.items(), key=lambda item: (item[0][0] is None, item[0][0] or 0))
    return [(day_title, _table(rows)) for (_, day_title), rows in ordered]
