from dataclasses import dataclass
from datetime import datetime
import pandas as pd
import numpy as np

from src.data import SESSION_CODES, TYRE_SESSIONS
from src.ui import get_schedule
from src.tyres import clean_laps

RACES = {
    "Hungaroring": "Hungarian Grand Prix",
    "Spa-Francorchamps": "Belgian Grand Prix",
    "Suzuka": "Japanese Grand Prix",
    "Marina Bay (Singapore)": "Singapore Grand Prix",
}

TYRE_OFFSET = {
    "Hungaroring": {"SOFT": -0.45, "MEDIUM": 0.0, "HARD": 0.55},
    "Suzuka": {"SOFT": -0.5,"MEDIUM": 0.0, "HARD": 0.45},
    "Spa-Francorchamps": {"SOFT": -0.45,"MEDIUM": 0.0, "HARD": 0.5},
    "Marina Bay (Singapore)":{"SOFT": -0.45,"MEDIUM": 0.0, "HARD": 0.55}
}

RACE_CODE = "R"

DRY_COMPOUNDS = ["SOFT", "MEDIUM", "HARD"]

MIN_RACE_LAPS = 100

FUEL_EFFECT = 0.05

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


def clean_laps_all_drivers(laps: pd.DataFrame, fuel_effect: float = FUEL_EFFECT, min_stint_laps: int = 1)-> pd.DataFrame:
    """Clean the laps for every driver and return them in a single table"""
    cleaned_laps = []
    for driver in laps["Driver"].unique():
        driver_laps = clean_laps(laps, driver, fuel_effect, min_stint_laps)
        cleaned_laps.append(driver_laps)
    return pd.concat(cleaned_laps, ignore_index= True)

def estimate_driver_pace_offset(race_laps: pd.DataFrame, base_pace: float, compound_params: dict, fuel_effect: float = FUEL_EFFECT, min_stint_laps: int = 3)->pd.DataFrame:
    clean = clean_laps_all_drivers(race_laps, fuel_effect, min_stint_laps)
    
    columns = ["Driver", "PaceOffset", "CleanLaps"]
    
    if clean.empty: 
        return pd.DataFrame(columns= columns)
    
    valid_laps = clean["Compound"].isin(compound_params.keys()) & clean["TyreLife"].notna()
    clean = clean[valid_laps].copy()
    
    if clean.empty: 
            return pd.DataFrame(columns= columns)
        
    compound_offset = {compound: params["offset"] 
                       for compound, params in compound_params.items()
                       }
    compound_degradation = { compound: params["degradation"]
                            for compound, params in compound_params.items()
                            }
    
    clean["ModelPace"] = (base_pace + clean["Compound"].map(compound_offset) + clean["Compound"].map(compound_degradation) * clean["TyreLife"])
    clean["PaceResidual"] = clean["LapTimeCorrect"] - clean["ModelPace"]
    
    driver_paces = (clean.groupby("Driver").agg(
        RawOffset = ("PaceResidual", "median"),
        CleanLaps = ("PaceResidual", "count")
        ).reset_index()
    )
    
    field_reference = driver_paces["RawOffset"].median()
    
    driver_paces["PaceOffset"] = driver_paces["RawOffset"] - field_reference
    
    return (driver_paces[columns].sort_values("PaceOffset").reset_index(drop = True))
    
def estimate_pit_loss(race_laps: pd.DataFrame)-> tuple:
    """Estimate green-flag pit loss (in seconds) as the median over all stops in race laps"""
    
    clean = clean_laps_all_drivers(race_laps)
    reference_pace = clean.groupby("Driver")["LapTimeSec"].median()
    
    green_laps = race_laps[race_laps["LapTime"].notna() & (race_laps["TrackStatus"] == "1")].copy()
    green_laps["LapTimeSec"] = green_laps["LapTime"].dt.total_seconds()
    
    pit_entries = green_laps[green_laps["PitInTime"].notna()]
    print("Pit entries with lap time: ", (race_laps["PitInTime"].notna() & race_laps["LapTime"].notna()).sum())
    print("Pit entries with green flag: ", len(pit_entries))
    
    losses = []
    transits = []
    skipped = []
    pit_details = []
    
    
    for i in range (len(pit_entries)):
        in_lap = pit_entries.iloc[i]
        driver = in_lap["Driver"]
        lap_number = in_lap["LapNumber"]
        
        if driver not in reference_pace.index: 
            skipped.append((driver, lap_number, "no reference pace"))
            continue
        
        if pd.notna(in_lap["PitOutTime"]):
            skipped.append((driver, lap_number, "In-lap is also an out-lap"))
            continue
        
        next_laps = race_laps[(race_laps["Driver"]== driver) & (race_laps["LapNumber"] == lap_number+1)]
        
        if next_laps.empty:
            skipped.append((driver, lap_number, "Following lap missing"))
            continue
        out_lap_candidates = next_laps[next_laps["PitOutTime"].notna()]
        if out_lap_candidates.empty: 
            skipped.append((driver, lap_number, "PitOutTime missing on next lap"))
            continue
        out_lap = out_lap_candidates.iloc[0]
        
        if out_lap["TrackStatus"] !="1":
            skipped.append((driver, lap_number, "Exit lap not with a green flag"))
            continue
        
        if pd.isna(out_lap["LapTime"]):
            skipped.append((driver, lap_number, "Lap time of exit lap missing"))
            continue
        
        out_lap_time_sec = out_lap["LapTime"].total_seconds()
        
        loss = in_lap["LapTimeSec"] + out_lap_time_sec - 2 * reference_pace[driver]
        losses.append(loss)
        
        transit = (out_lap["PitOutTime"] - in_lap["PitInTime"]).total_seconds()
        transits.append(transit)
        
        pit_details.append({
            "Driver": driver,
            "Lap": lap_number,
            "Loss": loss,
            "Transit": transit,
            })
        
    if len(losses) == 0: 
        return float("nan"), pd.DataFrame(), pd.DataFrame()
    
    print("Valid pit stops:")
    for stop in sorted(pit_details, key=lambda item: item["Loss"]):
        print(
            f"{stop['Driver']} lap {stop['Lap']}: "
            f"loss {stop['Loss']:.3f}s, "
            f"transit {stop['Transit']:.3f}s"
        )
    
    print("Excluded pit stops: ", len(skipped))
    for driver, lap_number, reason in skipped: 
        print(f"Excluded: {driver}, lap {lap_number}: {reason}")
    
    stops_table = pd.DataFrame(pit_details)
    skipped_table = pd.DataFrame(skipped, columns=["Driver", "Lap", "Reason"])
    return float(np.median(losses)), stops_table, skipped_table
    
def clean_sessions(laps_by_sessions: dict, fuel_effect: float = FUEL_EFFECT, min_stint_laps: int = 3)-> pd.DataFrame:
    """Clean every session on its own and put the results in one table"""
    
    cleaned = []
    for code, laps in laps_by_sessions.items():
        session_laps = clean_laps_all_drivers(laps, fuel_effect, min_stint_laps)
        session_laps["Session"] = code
        cleaned.append(session_laps)
    return pd.concat(cleaned, ignore_index=True)

def calibrate_tyre_degradation(laps_by_session: dict, fuel_effect: float = FUEL_EFFECT, min_stint_laps = 3)->pd.DataFrame:
    """Estimate tyre pace and degradation from available practice sessions"""
    
    cleaned = clean_sessions(laps_by_session,fuel_effect, min_stint_laps)
    cleaned = cleaned[cleaned["Compound"].isin(DRY_COMPOUNDS)]
    
    
    if cleaned.empty: 
        return pd.DataFrame(columns=["Compound", "Degradation", "Drivers", "Stints", "Laps", "BasePace"])
    
    required = {"Driver", "Session", "Stint", "Compound", "TyreLife", "LapTimeCorrect"}
    missing = required - set(cleaned.columns)
    if missing: 
        raise ValueError(f"Missing columns to estimate degradation: {sorted(missing)}")
    
    stint_rows = []
    
    for (driver, session, stint), stint_laps in cleaned.groupby(["Driver","Session", "Stint"]):
        stint_laps = stint_laps.dropna(subset=["TyreLife", "LapTimeCorrect", "Compound"])
        
        if len(stint_laps) < 2 or stint_laps["TyreLife"].nunique()<2: 
            continue
        
        slope, intercept = np.polyfit(stint_laps["TyreLife"].astype(float), stint_laps["LapTimeCorrect"].astype(float), 1)
        
        stint_rows.append({
            "Driver": driver, 
            "Session": session,
            "Stint": stint, 
            "Compound": stint_laps["Compound"].iloc[0],
            "BasePace": intercept,
            "Degradation": slope,
            "Laps": len(stint_laps)
        })
        
    stint_results = pd.DataFrame(stint_rows)
        
    if stint_results.empty: 
        return pd.DataFrame(columns=["Compound", "Degradation", "Drivers", "Stints", "Laps", "BasePace"])
    
    driver_result = (stint_results.groupby(["Driver", "Compound"],as_index= False).agg(
        Degradation = ("Degradation", "median"), Stints = ("Stint", "count"), Laps=("Laps", "sum"), BasePace=("BasePace", "median")
        )
    )
    
    calibration = (driver_result.groupby("Compound", as_index= False).agg(
        Degradation=("Degradation", "median"), Drivers=("Driver", "nunique"), Stints=("Stints", "sum"), Laps=("Laps", "sum"), BasePace=("BasePace", "median")
        ).sort_values("Compound").reset_index(drop=True)
    )
    
    print(stint_results.groupby("Compound").size())
    return calibration
    

def build_degradation_model(practice: pd.DataFrame, race: pd.DataFrame)-> pd.DataFrame:
    """One degradation value per compound: race value if it has enough laps,
    otherwise practice value. Degradation is never below zero."""
    rows = []
    for compound in DRY_COMPOUNDS:
        in_race = race[race["Compound"] == compound]
        in_practice = practice[practice["Compound"] == compound]
        
        if not in_race.empty and in_race["Laps"].iloc[0] >= MIN_RACE_LAPS:
            degradation = in_race["Degradation"].iloc[0]
            source = 'race'
        elif not in_practice.empty: 
            degradation = in_practice["Degradation"].iloc[0]
            source = 'practice'
        else:
            continue
        rows.append({"Compound": compound, "Degradation": max(degradation, 0.0), "Source": source})
    return pd.DataFrame(rows)

