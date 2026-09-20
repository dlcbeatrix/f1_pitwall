import fastf1
import streamlit as st
import plotly.express as px
import pandas as pd

from datetime import datetime


from src.data import (DEFAULT_COLOR, RACE_LIKE, SESSION_LABELS, download_laps, event_sessions, laps_path, team_color_map)
from src.tyres import clean_laps


COMPOUND_COLORS = {
    "SOFT": "#e10600", "MEDIUM": "#f5c400", "HARD": "#888888",
    "INTERMEDIATE": "#43b02a", "WET": "#0067ad",
}

@st.cache_data(ttl = 3600, show_spinner=False)
def get_schedule(year:int):
    try:
        return fastf1.get_event_schedule(year, include_testing= False)
    except Exception: 
        return None

@st.cache_data(show_spinner=False)
def read_laps(path:str) -> pd.DataFrame:
    return pd.read_parquet(path)

#Main page title
st.title('Tyre Degradation Analysis')

#Sidebar setup 
st.sidebar.header('Session Settings')
#1. Season
years = list(range(datetime.now().year, 2017, -1))
year = st.sidebar.selectbox("Season", years, index= None, placeholder= "Select a year")

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
event = past[past["EventName"] == gp_name].iloc[0]   # the row of the chosen GP

rnd = int(event["RoundNumber"])
sessions = event_sessions(event)

#3. Session
code = st.sidebar.selectbox("Session", sessions, format_func = lambda c: SESSION_LABELS[c], index= None, placeholder= "Select a session")

path = laps_path(year, rnd, code)
if not path.exists():
    st.info("This session is not saved yet. Downloading takes a minute or so.")
    if st.button(" Download session"):
        with st.spinner("Downloading from the F1 servers..."):
            status = download_laps(year, rnd, code)
        if status == "failed":
            st.error("Download failed. Try another session or check your connection.")
            st.stop()
        st.rerun()
    st.stop()

laps = read_laps(str(path))
colors = team_color_map(laps)
title = f"{gp_name} {year} - {SESSION_LABELS[code]}"

#MODULE 1: TYRE DEGRADATION 
#1.1 QUALI
if code not in RACE_LIKE:
    st.subheader(title)
    q = laps.dropna(subset=["LapTime"])
    if "Deleted" in q.columns:
        q = q[q["Deleted"]== False]
        
        if q.empty: 
            st.warning('No valid laps in this session')
            st.stop()
            
        q["Seconds"] = q["LapTime"].dt.total_seconds()
    
    best = q.sort_values("Seconds").drop_duplicates(subset="Driver")
    
    best["Gap"] = best["Seconds"] - best["Seconds"].min()
    
    #Bar chart, one bar per driver coloured by team and sorted by gap
    fig = px.bar(best, x="Driver", y="Gap", color = "Team", color_discrete_map= colors, labels={"Gap" : "Gap to fastest lap(s)"})
    fig.update_xaxes (categoryorder = "total ascending")
    st.plotly_chart(fig)
    
    st.caption("Tyre degradation is only available for races and sprints")
    st.stop()
    
#1.2 RACE AND SPRINTS
driver = st.sidebar.selectbox("Driver", sorted(laps["Driver"].unique()), index= None, placeholder= "Select a driver")
fuel_k = st.sidebar.slider("Fuel effect (s/lap)", 0.0, 0.08, 0.05, 0.005)

race_laps = clean_laps(laps, driver, fuel_k)
if race_laps.empty: 
    st.warning('No valid laps for this driver')
    st.stop()
    
team = race_laps["Team"].iloc[0]
team_color = colors.get(team, DEFAULT_COLOR)

st.markdown(f"<h3 style='border-left: 8px solid {team_color}; padding-left: 12px'>"
    f"{driver} · {team} — {title}</h3>",
    unsafe_allow_html=True,)

fig = px.scatter(race_laps, x = "LapNumber", y="LapTimeCorrect", color = "Compound",
                 hover_data=["Stint", "TyreLife"],
                 color_discrete_map=COMPOUND_COLORS,
                 labels={"LapNumber": "Lap", "LapTimeCorr": "Fuel-corrected lap time(s)"})

fig.update_traces(marker=dict(size = 10, line=dict(width=2, color=team_color)))
st.plotly_chart(fig)

st.dataframe(race_laps[["LapNumber", "Stint", "Compound", "TyreLife", "LapTimeSec", "LapTimeCorrect"]])