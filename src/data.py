import fastf1
import pandas as pd
import os
import streamlit as st
from fastf1.exceptions import DataNotLoadedError

fastf1.set_log_level('WARNING')

#Cache configuration
if not os.path.exists('cache'):
    os.makedirs('cache')
fastf1.Cache.enable_cache('cache')

@st.cache_data(show_spinner=False)
def load_laps(year: int, gp: str, session_type: str):
    #loading info session but telemetry, weather or messages are false to have a faster download
    session = fastf1.get_session(year, gp, session_type)
    session.load(telemetry = False, weather = False, messages = False)
    try: 
        return session.laps
    except DataNotLoadedError: 
        raise RuntimeError('Download Failed')
    

if __name__ == "__main__":
    print('Starting test: Monza 24 Race')
    test_laps = load_laps(2024, 'Monza', 'R')

    
    print('\n Data saved with success. Keywords: ')
    cols = ['Driver', 'LapNumber', 'LapTime', 'Compound', 'TyreLife', 'Stint', 'PitInTime', 'PitOutTime', 'TrackStatus']
    print(test_laps[cols].head())
    print("\nPiloti:", sorted(test_laps['Driver'].unique()))
    print("Mescole:", test_laps['Compound'].unique())