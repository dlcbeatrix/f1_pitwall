import streamlit as st
import pandas as pd
from src.calibration import find_session_sources, RACE_CODE, RACES, estimate_pit_loss, calibrate_tyre_degradation
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

lap_frames = []

for code, laps in practice_laps.items():
    laps = laps.copy()
    laps["Session"] = code
    lap_frames.append(laps)
    
race_laps_for_calibration = race_laps.copy()
race_laps_for_calibration["Session"] = RACE_CODE
lap_frames.append(race_laps_for_calibration)

simulation_laps = pd.concat(lap_frames, ignore_index = True)

pit_loss = estimate_pit_loss(race_laps)
st.metric("Pit stop loss with green flag", f"{pit_loss:.1f} s")

tyre_calibration = calibrate_tyre_degradation(simulation_laps)
print(tyre_calibration)
    