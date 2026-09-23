import fastf1
try:
    fastf1.config.Set("core", "data_source", "jolpica")
except AttributeError:
    pass 

import fastf1.plotting
import pandas as pd
import traceback


from pathlib import Path

fastf1.set_log_level('WARNING')

DATA_DIR = Path("data/laps")
CACHE_DIR = Path("cache")
SPEED_DIR = Path("data/speed")
DEFAULT_COLOR = "gray"

COLUMNS = [
    "Driver", "DriverNumber", "Team", "LapNumber", "LapTime", "Stint",
    "Compound", "TyreLife", "PitInTime", "PitOutTime",
    "Sector1Time", "Sector2Time", "Sector3Time", "TrackStatus", "Deleted",
]

SESSION_CODES = {
    "Practice 1": "FP1", "Practice 2": "FP2", "Practice 3": "FP3", "Sprint Shootout": "SS", 
    "Sprint Qualifying" : "SQ", "Sprint": "S", "Qualifying" : "Q", "Race": "R",
}
SESSION_LABELS = {code: name for name, code in SESSION_CODES.items()}
TYRE_SESSIONS = {"FP1", "FP2", "FP3", "S", "R"}   # sessions shown in Tyre Degradation
QUALI_SESSIONS = {"Q", "SQ", "SS"}                # sessions shown in Qualifying Gap

def enable_cache():
    CACHE_DIR.mkdir(exist_ok= True)
    fastf1.Cache.enable_cache(str(CACHE_DIR))

def laps_path(year: int, rnd: int, code: str) -> Path: 
    return DATA_DIR / f"{year}_{rnd:02d}_{code}.parquet"

def event_sessions(event) ->list:
    ###session codes of a schedule row
    codes = []
    for i in range(1,6):
        code = SESSION_CODES.get(event.get(f"Session{i}"))
        if code:
            codes.append(code)
    return codes



def download_laps(year: int, rnd: int, code: str) -> str:
    """Download one session and save its laps as parquet.
    Returns 'exists', 'saved' or 'failed'."""
    path = laps_path(year, rnd, code)
    if path.exists():
        return "exists"
    try:     
        session = fastf1.get_session(year, rnd, code)
        session.load(telemetry = False, weather = False)
        laps = pd.DataFrame(session.laps)
        if laps.empty: 
            return "failed"
        if "Deleted" in laps.columns: 
            laps["Deleted"] = laps["Deleted"].fillna(False).astype(bool)
        
        # Official team colours (grey if a team is not recognised)    
        colors = {}
        for team in laps["Team"].dropna().unique():
            try: 
                colors[team] = fastf1.plotting.get_team_color(team, session = session)
            except Exception: 
                colors[team] = DEFAULT_COLOR
        laps["TeamColor"] = laps["Team"].map(colors).fillna(DEFAULT_COLOR)
        
        cols = [c for c in COLUMNS if c in laps.columns] + ["TeamColor"]
        DATA_DIR.mkdir(parents= True, exist_ok = True)
        laps[cols].to_parquet(path, index=False)
        return "saved"
    except Exception as e: 
        print(f"Download error: {type(e).__name__}: {e}")
        return "failed"
    

def team_color_map(laps: pd.DataFrame) -> dict:
    """{team name: hex colour} for the teams in a laps table."""
    if "TeamColor" not in laps.columns:
        return {t: DEFAULT_COLOR for t in laps["Team"].dropna().unique()}
    return dict(zip(laps["Team"], laps["TeamColor"]))

def speed_path(year: int, rnd: int, code: str, driver: str)->Path: 
    return SPEED_DIR /f"{year}_{rnd:02d}_{code}_{driver}.parquet"

def download_speed(year: int, rnd: int, code: str, driver: str)->str:
    """Save time and speed of the fastest lap of a driver. This needs telemetry.
    Returnn 'exists', 'saved' or 'failed'."""
    
    path = speed_path(year, rnd, code, driver)
    if path.exists():
        return 'exists'
    try: 
        session = fastf1.get_session(year, rnd, code)
        session.load(laps=True, telemetry = True, weather ="False", messages = "False")
        fastest = session.laps.pick_drivers(driver).pick_fastest()
        car_data = fastest.get_car_data()
        trace = pd.DataFrame({
            "Time": car_data["Time"].dt.total_seconds(),
            "Speed": car_data["Speed"],
        })
        SPEED_DIR.mkdir(parents=True, exist_ok = True)
        trace.to_parquet(path, index = False)
        return 'saved'
    except Exception as e: 
        print(f'Speed download error: {type(e).__name__}: {e}')
        traceback.print_exc()
        return 'failed'