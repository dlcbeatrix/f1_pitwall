import pandas as pd

def clean_laps(laps: pd.DataFrame, driver: str, fuel_effect: float = 0.03) -> pd.DataFrame:
    #return the laps of a driver that are suitable for tyre degradation analysis
    driver_laps = laps[laps["Driver"] == driver].copy()
    
    driver_laps = driver_laps[driver_laps["LapTime"].notna()]                                       #laps with no time
    driver_laps = driver_laps[driver_laps["PitInTime"].isna() & driver_laps['PitOutTime'].isna()]   #remove in and out-laps
    driver_laps = driver_laps[driver_laps["TrackStatus"]== "1"]                                     #green track
    driver_laps = driver_laps[driver_laps['LapNumber']> 1]
    
    driver_laps['LapTimeSec'] = driver_laps['LapTime'].dt.total_seconds()   #lap time in seconds
    
    #remove very slow laps
    driver_laps = driver_laps[driver_laps["LapTimeSec"] < 1.07 * driver_laps['LapTimeSec'].median()]
    
    #fuel correction as the car gets lighter
    
    driver_laps['LapTimeCorrect'] = driver_laps['LapTimeSec'] + fuel_effect * driver_laps['LapNumber']
    
    return driver_laps