from datetime import datetime

import fastf1
import pandas as pd
import streamlit as st

from src.data import (SESSION_LABELS, download_laps, event_sessions, laps_path, download_speed, speed_path)

@st.cache_data(ttl = 3600, show_spinner=False)
def get_schedule(year:int):
    try:
        return fastf1.get_event_schedule(year, include_testing= False)
    except Exception: 
        return None

@st.cache_data(show_spinner=False)
def read_laps(path:str) -> pd.DataFrame:
    return pd.read_parquet(path)

def format_time(seconds:float) -> str: 
    #es 78.553 -> '1:18:553' minutes:seconds:milliseconds
    total_ms = round(seconds *1000)
    minutes, rest_ms = divmod(total_ms, 60000)
    secs, ms = divmod(rest_ms, 1000)
    return f"{minutes}:{secs:02d}.{ms:03d}"

def session_selector(allowed_codes):
    """Draw Season / Grand Prix / Session menus in the sidebar.
    Stops the page until all three are chosen.
    Returns: year, round number, Grand Prix name, session code."""
    
    #Sidebar setup 
    st.sidebar.header('Session Settings')
    #1. Season
    years = list(range(datetime.now().year, 2017, -1))
    year = st.sidebar.selectbox("Season", years, index= None, placeholder= "Select a year")
    if year is None: 
        st.info("Select a season in the sidebar to start.")
        st.stop()
    #2. Grand Prix 
    schedule = get_schedule(year)
    if schedule is None: 
        st.error("Could not load the race calendar")
        st.stop()

    today = datetime.now().date()
    past = schedule[schedule["EventDate"].dt.date < today]

    if past.empty:
        st.info("No races available for this season yet.")
        st.stop()

    gp_name = st.sidebar.selectbox("Grand Prix", past["EventName"], index= None, placeholder= "Select a Grand Prix")
    if gp_name is None: 
        st.info("Select a GP")
        st.stop()
    event = past[past["EventName"] == gp_name].iloc[0]   # the row of the chosen GP

    rnd = int(event["RoundNumber"])

    #3. Session
    sessions = [c for c in event_sessions(event) if c in allowed_codes]
    code = st.sidebar.selectbox("Session", sessions, format_func = lambda c: SESSION_LABELS[c], index= None, placeholder= "Select a session")

    if not code: 
        st.stop()
        
    return year, rnd, gp_name, code

def get_laps(year: int, rnd: int, code:str)-> pd.DataFrame:
    """Return the laps of a session. If it is not saved yet, show a Download button."""
    path = laps_path(year, rnd, code)
    if not path.exists():
        st.info("This session is not saved yet. Downloading takes a minute or so.")
        if st.button("Download session", icon=":material/download:"):
            with st.spinner("Downloading from the F1 servers..."):
                status = download_laps(year, rnd, code)
            if status == "failed":
                st.error("Download failed. Try another session or check your connection.")
                st.stop()
            st.rerun()
        st.stop()
    return read_laps(str(path))

#NOISY RADIO
@st.cache_data(show_spinner=False)
def read_speed(path: str) -> pd.DataFrame:
    return pd.read_parquet(path)

def get_speed(year: int, rnd: int, code:str, driver:str)-> pd.DataFrame:
    """Return time and speed of the fastest lap."""
    path = speed_path(year, rnd, code, driver)
    if not path.exists():
        st.info('The telemetry of the selected driver is not saved yet. Downloading can take a couple of minutes.')
        if st.button("Download Telemetry", icon=":material/download:"):
            with st.spinner("Downloading telemetry from the F1 servers..."):
                status = download_speed(year, rnd, code, driver)
            if status == 'failed':
                st.error('Download failed. Try another driver or session')
                st.stop()
            st.rerun()
        st.stop()
    return read_speed(str(path))
        