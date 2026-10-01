import streamlit as st
import pandas as pd

from src.calibration import (find_session_sources, RACE_CODE, RACES, estimate_pit_loss, calibrate_tyre_degradation, build_degradation_model, 
                             DRY_COMPOUNDS, TYRE_OFFSET, estimate_driver_pace_offset)
from src.ui import race_selector, get_laps, show_sessions_status, format_time
from src.strategy import simulate_strategy, generate_strategies

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

degradation_by_compound = dict(zip(degradation_model["Compound"], degradation_model["Degradation"]))
source_by_compound = dict(zip(degradation_model["Compound"], degradation_model["Source"])) 

st.sidebar.header("Tyre assumptions")
compound_params={}
for compound in DRY_COMPOUNDS:
    default_degradation = float(degradation_by_compound.get(compound, 0.05))
    degradation = st.sidebar.slider(f"{compound.title()} degradation (s/lap)", 0.0, 0.15, default_degradation, 0.005)
    
    if compound == "MEDIUM":
        offset = 0.0
    else: 
        offset = st.sidebar.slider(f"{compound.title()} pace vs Medium (s/lap)", -1.0, 1.0, float(TYRE_OFFSET[label][compound]), 0.05)
    
    compound_params[compound] = {"offset": offset, "degradation": degradation}
    
    medium = race_calibration[race_calibration["Compound"] == "MEDIUM"]
if medium.empty or pd.isna(pit_loss):
    st.warning("Missing Medium race data or pit loss: cannot simulate")
    st.stop()
base_pace = medium["BasePace"].iloc[0]

total_laps = int(race_laps["LapNumber"].max())
tyre_laps = race_laps[race_laps["Compound"].isin(DRY_COMPOUNDS) & race_laps["TyreLife"].notna()]
stint_max_ages = (tyre_laps.groupby(["Driver", "Stint", "Compound"])["TyreLife"]).max().reset_index(name="MaxTyreLife")
driver_max_ages = (stint_max_ages.groupby(["Driver", "Compound"])["MaxTyreLife"]).max().reset_index(name = "LongestStint")

compound_limits = (driver_max_ages.groupby("Compound")["LongestStint"].median().round().astype(int))

pit_windows = {}

for compound, typical_max in compound_limits.items():
    if typical_max < 8 : 
        pit_windows[compound] = None
    else:
        pit_windows[compound] = (
            max(8, int(typical_max)-3), int(typical_max)+3
        )

window_table = pd.DataFrame([{
    "Compound": compound, 
    "Typical max tyre age": int(compound_limits[compound]),
    "Pit window": (
            "Insufficient data"
            if pit_windows[compound] is None
            else f"{pit_windows[compound][0]}–{pit_windows[compound][1]} laps"
        )
    }
    for compound in compound_limits.index
])
st.subheader("Stint duration estimated from the race")
st.dataframe(window_table, hide_index=True)

driver_offsets = estimate_driver_pace_offset(race_laps, base_pace, compound_params, fuel_effect= 0.05)
if driver_offsets.empty: 
    st.warning("No clean laps available to estimate driver pace")
    st.stop()
    
selected_driver = st.sidebar.selectbox("Select Driver", driver_offsets["Driver"].tolist())
selected_row = driver_offsets[driver_offsets["Driver"] == selected_driver].iloc[0]

driver_offset = selected_row["PaceOffset"]
driver_base_pace = base_pace + driver_offset

st.metric(f"{selected_driver} pace offset", f"{driver_offset:+.3f} s/lap",)

with st.expander("Driver pace offsets"):
    display_offsets = driver_offsets.copy()
    display_offsets["PaceOffset"] = display_offsets["PaceOffset"].apply(lambda value: f"{value:+.3f} s/lap")
    st.dataframe(display_offsets, hide_index= True)

strategies = generate_strategies(DRY_COMPOUNDS, total_laps, 2)
max_stint_laps = {}
for compound, window in pit_windows.items():
    if window is not None:
        max_stint_laps[compound] = window[1]

strategies = [
    strategy
    for strategy in strategies
    if all(
        compound in max_stint_laps and laps <= max_stint_laps[compound]
        for compound, laps in strategy
    )
]

strategy_results = []

for strategy in strategies: 
    lap_times = simulate_strategy(strategy, driver_base_pace, compound_params, pit_loss)
    strategy_results.append({
        "Strategy": "->".join(f"{compound} ({laps})" 
                               for compound, laps in strategy),
        "TotalTime": sum(lap_times),
        "Stints": strategy,
    })
    
strategy_results.sort(key=lambda result: result["TotalTime"])

st.write(f"Simulated strategies: {len(strategy_results)}")
st.dataframe([
    {
        "Strategy": result["Strategy"],
        "Total Time": format_time(result["TotalTime"]),
    } for result in strategy_results[:10]
], hide_index= True)


