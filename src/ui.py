from datetime import datetime

import fastf1
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from src.data import (SESSION_LABELS, download_laps, event_sessions, laps_path, download_speed, speed_path, COMPOUND_COLORS)

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

def show_sessions_status(sessions: list):
    """Shows which sessions are saved and a download button for the missing ones. 
    sessions: list of (year, round, code). Stops the page if any is missing"""
    
    missing = []
    for year, rnd, code in sessions: 
        name = f"{year} {SESSION_LABELS[code]}"
        
        if laps_path(year, rnd, code).exists():
            st.success(f"{name}: data already saved", icon = ":material/check_circle:")
        else:
            missing.append((year, rnd, code))
            st.warning(f"{name}: not saved yet")

    if missing:
        if st.button("Download missing sessions", icon=":material/download:"):
            failed = []
            with st.spinner("Downloading from the F1 servers, it can take a few minutes..."):
                for year, rnd, code in missing:
                    status = download_laps(year, rnd, code)
                    if status == "failed":
                        failed.append(f"{year} {SESSION_LABELS[code]}")
            if failed:
                st.error("Download failed for: " + ", ".join(failed))
            else:
                st.rerun()
        st.stop()
                

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

#RACE STRATEGY
def race_selector(races: dict):
    """Draw a menu with only the given races in the sidebar. Stops the page until one is chosen."""
    
    st.sidebar.header("Race")
    label = st.sidebar.selectbox("Circuit", list(races.keys()), index = None, placeholder="Select a circuit")
    if label is None: 
        st.info("Select a circuit in the sidebar to start")
        st.stop()
    return label, races[label]
        
def strategy_bar_chart(results: list):
    """Horizontal stacked bars: one row per strategy, one segment per stint."""
    fig = go.Figure()
    shown = set()
    for result in results:
        for compound, laps in result["Stints"]:
            fig.add_trace(go.Bar(
                y=[result["Strategy"]], x=[laps], orientation="h",
                name=compound, marker_color=COMPOUND_COLORS[compound],
                text=[laps], textposition="inside",
                legendgroup=compound, showlegend=compound not in shown,
            ))
            shown.add(compound)
    fig.update_layout(barmode="stack", xaxis_title="Laps",
                      yaxis=dict(autorange="reversed"),
                      height=max(300, 28 * len(results) + 120))
    return fig