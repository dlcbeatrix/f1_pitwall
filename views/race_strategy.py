import streamlit as st
import pandas as pd
from src.calibration import find_session_sources, RACE_CODE, RACES, estimate_pit_loss, calibrate_tyre_degradation, build_degradation_model
from src.ui import race_selector, get_laps, show_sessions_status, format_time

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

all_laps = practice_laps.copy()
all_laps[RACE_CODE] = race_laps

pit_loss, pit_stops, pit_skipped = estimate_pit_loss(race_laps)
if pd.isna(pit_loss):
     st.metric("Pit stop loss with green flag", "n/a")
else:
    st.metric("Pit stop loss with green flag", format_time(pit_loss))
st.caption(f"Median over {len(pit_stops)} green-flag pit-stops")
with st.expander("Pit stop details: "):
    st.dataframe(pit_stops, hide_index= True)
    st.write("Excluded stops: ")
    st.dataframe(pit_skipped, hide_index=True)

practice_calibration = calibrate_tyre_degradation(practice_laps, fuel_effect=0.0)
race_calibration = calibrate_tyre_degradation({RACE_CODE: race_laps}, fuel_effect=0.05)


degradation_model = build_degradation_model(practice_calibration, race_calibration)
display_deg = degradation_model.copy()
display_deg["Degradation"] = display_deg["Degradation"].apply(lambda d: f"{d:+.3f} s/lap")
st.write("Final Degradation Data: ")
st.dataframe(display_deg, hide_index=True)

with st.expander("Calibration details"):
    display_fp = practice_calibration.copy()
    display_fp["BasePace"] = display_fp["BasePace"].apply(format_time)
    display_fp["Degradation"] = display_fp["Degradation"].apply(lambda d: f"{d:+.3f} s/lap")
    st.write("Tyre degradation during FP:")
    st.dataframe(display_fp, hide_index=True)

    display_race = race_calibration.copy()
    display_race["BasePace"] = display_race["BasePace"].apply(format_time)
    display_race["Degradation"] = display_race["Degradation"].apply(lambda d: f"{d:+.3f} s/lap")
    st.write("Tyre degradation during the Race:")
    st.dataframe(display_race, hide_index=True)