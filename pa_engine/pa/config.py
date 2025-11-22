# pa_engine/pa/config.py

from dataclasses import dataclass
from typing import List, Optional


# FX Daily open time in UTC
FX_DAILY_OPEN_UTC = 22  # 22:00 UTC = Sydney open → start of new Forex day


@dataclass
class SessionDef:
    name: str
    open_utc: int   # hour in [0, 23]
    close_utc: int  # hour in [0, 23]
    priority: int   # higher = matched first


def _hour_in_range(hr: int, open_hr: int, close_hr: int) -> bool:
    """
    Check if 'hr' is within [open_hr, close_hr) on a 24h clock.
    Handles wrap-around (e.g. 21→06 for Sydney).
    """
    if open_hr <= close_hr:
        return open_hr <= hr < close_hr
    else:
        # wrap-around (e.g., 21→06)
        return hr >= open_hr or hr < close_hr


# Central session configuration (UTC, no DST)
FX_SESSIONS: List[SessionDef] = [
    
    SessionDef(name="ASIA", open_utc=22, close_utc=8, priority=70),
    SessionDef(name="LONDON", open_utc=8, close_utc=13, priority=80),
    # Overlaps first (highest priority)
    SessionDef(name="NY_OVERLAP", open_utc=13, close_utc=16, priority=100),
    # Major sessions
    SessionDef(name="NY", open_utc=16, close_utc=22, priority=90)
    
]


def session_for_hour(hr: int) -> str:
    """
    Return FX session label for a given UTC hour, using FX_SESSIONS config.

    Priority:
      - We sort by 'priority' descending and return the first match.
      - If nothing matches (shouldn't really happen), return 'OTHER'.
    """
    for sess in sorted(FX_SESSIONS, key=lambda s: s.priority, reverse=True):
        if _hour_in_range(hr, sess.open_utc, sess.close_utc):
            return sess.name
    return "OTHER"
