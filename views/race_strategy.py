import streamlit as st
from src.calibration import find_session_sources, RACE_CODE, RACES
from src.ui import race_selector, get_laps, show_sessions_status

st.title("Race Stategy Predictor")

label, event_name = race_selector(RACES)
sources = find_session_sources(event_name)

if sources.race_year is None or sources.practice_year is None: 
    st.warning("No saved practice or race data found for this circuit")
    st.stop()
    
sessions = [(sources.race_year, sources.race_round, RACE_CODE)]
for code in sources.practice_sessions:
    sessions.append((sources.practice_year, sources.practice_round, code))

st.subheader(f"Data used for {label}:")
show_sessions_status(sessions)

race_laps = get_laps(sources.race_year, sources.race_round, RACE_CODE)

practice_laps = {}
for code in sources.practice_sessions: 
    practice_laps[code] = get_laps(sources.practice_year, sources.practice_round, code)