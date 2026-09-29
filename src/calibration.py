from dataclasses import dataclass
from datetime import datetime
import pandas as pd

from src.data import SESSION_CODES, TYRE_SESSIONS
from src.ui import get_schedule

RACES = {
    "Hungaroring": "Hungarian Grand Prix",
    "Spa-Francorchamps": "Belgian Grand Prix",
    "Suzuka": "Japanese Grand Prix",
    "Marina Bay (Singapore)": "Singapore Grand Prix",
}

RACE_CODE = "R"

@dataclass
class SessionSources: 
    practice_year: int | None
    practice_round: int | None
    practice_sessions: list[str]
    race_year: int | None
    race_round: int | None
    
def finished_sessions(event)-> list: 
    """Codes of the sessions of an event that have already taken place"""
    now = pd.Timestamp.now("UTC").tz_localize(None)
    done = []
    for i in range (1, 6):
        code = SESSION_CODES.get(event.get(f"Session{i}"))
        start = event.get(f"Session{i}DateUtc")
        if code and pd.notna(start) and start + pd.Timedelta(hours = 3) < now: 
            done.append(code)
    return done

    
def find_session_sources(event_name: str)-> SessionSources:
    """Find the latest availabe practice session and race for a target GP"""
    practice_year, practice_round, practice_sessions = None, None, []
    race_year, race_round = None, None
    
    for year in range (datetime.now().year, 2017, -1):
        schedule = get_schedule(year)
        if schedule is None: 
            continue
        matches = schedule[schedule["EventName"]== event_name]
        if matches.empty: 
            continue
        
        event = matches.iloc[0]
        done = finished_sessions(event)
        
        practice = [c for c in done if c in TYRE_SESSIONS and c != RACE_CODE]
        if practice_year is None and practice: 
            practice_year = year
            practice_round = int(event["RoundNumber"])
            practice_sessions = practice
            
        if race_year is None and RACE_CODE in done: 
            race_year = year
            race_round = int(event["RoundNumber"])
            
        if practice_year is not None and race_year is not None: 
            break
    return SessionSources(practice_year, practice_round, practice_sessions, race_year, race_round)


def calibrate_tyre_degradation(laps_by_session: dict[str, pd.DataFrame])->pd.DataFrame:
    """Estimate tyre pace and degradation from available practice sessions"""
    raise NotImplementedError

def estimate_pit_loss(race_laps: pd.DataFrame)-> float:
    """Estimate green-flag pit loss from race laps"""
    raise NotImplementedError

def build_calibration(target_year: int, round_number: int)-> dict: 
    """Build the calibration inputs for one target event"""
    raise NotImplementedError
    

