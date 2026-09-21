import pandas as pd
import numpy as np

def clean_laps(laps: pd.DataFrame, driver: str, fuel_effect: float = 0.03, min_stint_laps: int = 1) -> pd.DataFrame:
    #return the laps of a driver that are suitable for tyre degradation analysis
    driver_laps = laps[laps["Driver"] == driver].copy()
    
    driver_laps = driver_laps[driver_laps["LapTime"].notna()]                                       #laps with no time
    driver_laps = driver_laps[driver_laps["PitInTime"].isna() & driver_laps['PitOutTime'].isna()]   #remove in and out-laps
    driver_laps = driver_laps[driver_laps["TrackStatus"]== "1"]                                     #green track
    driver_laps = driver_laps[driver_laps['LapNumber']>1]
    
    driver_laps['LapTimeSec'] = driver_laps['LapTime'].dt.total_seconds()   #lap time in seconds
    
    #remove very slow laps
    driver_laps = driver_laps[driver_laps["LapTimeSec"] < 1.07 * driver_laps['LapTimeSec'].median()]
    
    #keep only the stints that have at least min_stint_laps clean laps
    laps_in_stint = driver_laps.groupby("Stint")["LapNumber"].transform("count")
    driver_laps = driver_laps[laps_in_stint >= min_stint_laps]
    
    #fuel correction as the car gets lighter
    driver_laps['LapTimeCorrect'] = driver_laps['LapTimeSec'] + fuel_effect * driver_laps['LapNumber']
    
    return driver_laps

def tyres_degradation(driver_laps:pd.DataFrame)-> pd.DataFrame:
    """Degradation of each stint: slope (s/lap) of a straight line fitted to the corrected lap times."""
    rows = []
    for stint, stint_laps in driver_laps.groupby("Stint"):
        if len(stint_laps)<2:
            continue
        slope, intercept = np.polyfit(stint_laps["LapNumber"], stint_laps["LapTimeCorrect"], 1)
        rows.append({
            "Stint": int(stint),
            "Compound": stint_laps["Compound"].iloc[0],
            "Laps": len(stint_laps),
            "Degradation": slope,
            "Intercept": intercept,
        })
    return pd.DataFrame(rows)