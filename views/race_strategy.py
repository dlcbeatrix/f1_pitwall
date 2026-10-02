import streamlit as st
import pandas as pd
import plotly.express as px

from src.calibration import (find_session_sources, RACE_CODE, RACES, estimate_pit_loss, calibrate_tyre_degradation, build_degradation_model, 
                             DRY_COMPOUNDS, TYRE_OFFSET, estimate_driver_pace_offset, FUEL_EFFECT, empirical_degradation_curve)
from src.ui import race_selector, get_laps, show_sessions_status, format_time, strategy_bar_chart
from src.strategy import simulate_strategy, generate_strategies
from src.data import COMPOUND_COLORS

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
race_calibration = calibrate_tyre_degradation({RACE_CODE: race_laps}, FUEL_EFFECT)


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

st.subheader("Tyre wear curve")
st.caption("This section is still under construction: the tyre cliff is not detected automatically. "
           "Read on the curve the tyre age where the time lost starts to rise faster, and by how much, "
           "then set those values with the cliff sliders in the sidebar.")

include_practice = st.checkbox("Include practice sessions (noisy)", value=False)
curve_laps_by_session = {RACE_CODE: race_laps}
fuel_effect_by_session = {RACE_CODE: FUEL_EFFECT}
if include_practice:
    for code, laps in practice_laps.items():
        curve_laps_by_session[code] = laps
        fuel_effect_by_session[code] = 0.0

curve = empirical_degradation_curve(curve_laps_by_session, fuel_effect_by_session,
                                    min_stint_laps=6, min_stints_per_age=5)
if curve.empty:
    st.info("Not enough stints to draw the wear curve")
else:
    fig = px.line(curve, x="TyreLife", y="MedianTimeLost", color="Compound", 
                  line_dash = "Session", markers=True,
                  hover_data = ["Stints"],
                  color_discrete_map=COMPOUND_COLORS,
                  labels={"TyreLife": "Tyre age (laps)", "MedianTimeLost": "Time lost vs start of stint (s)", "Session": "Session", "Stints": "Indipendent stints"})
    st.plotly_chart(fig)

driver_offsets = estimate_driver_pace_offset(race_laps, base_pace, compound_params, FUEL_EFFECT)
if driver_offsets.empty: 
    st.warning("No clean laps available to estimate driver pace")
    st.stop()
    
selected_driver = st.selectbox("Select Driver", driver_offsets["Driver"].tolist())
selected_row = driver_offsets[driver_offsets["Driver"] == selected_driver].iloc[0]

driver_offset = selected_row["PaceOffset"]
driver_base_pace = base_pace + driver_offset

st.metric(f"{selected_driver} pace offset", f"{driver_offset:+.3f} s/lap",)

with st.expander("Driver pace offsets"):
    display_offsets = driver_offsets.copy()
    display_offsets["PaceOffset"] = display_offsets["PaceOffset"].apply(lambda value: f"{value:+.3f} s/lap")
    st.dataframe(display_offsets, hide_index= True)

strategies = generate_strategies(DRY_COMPOUNDS, total_laps, 2)

st.sidebar.header("Maximum stint length")
max_stint_laps = {}
for compound in DRY_COMPOUNDS: 
    window = pit_windows.get(compound)
    default_max = window[1] if window is not None else 20
    default_max = max(8, min(default_max, total_laps))
    max_stint_laps[compound] = st.sidebar.slider(f"{compound.title()} max stint(laps)", 8, total_laps, default_max, 1)
    

strategies = [
    strategy for strategy in strategies
    if all( laps <= max_stint_laps[compound] for compound, laps in strategy)
]


best_by_sequence = {}
st.sidebar.header("Tyre cliff")
knee_ages = {}
for compound in DRY_COMPOUNDS:
    typical = int(compound_limits[compound]) if compound in compound_limits.index else 15
    typical = max(5, min(typical, total_laps))
    knee_ages[compound] = st.sidebar.slider(f"{compound.title()} cliff age (laps)", 5, total_laps, typical, 1)

cliff_slope = st.sidebar.slider("Extra wear after the cliff (s/lap per lap)", 0.0, 0.3, 0.0, 0.01)

for strategy in strategies: 
    lap_times = simulate_strategy(
    strategy,
    driver_base_pace,
    compound_params,
    pit_loss,
    knee_ages=knee_ages,
    cliff_slope=cliff_slope,
)
    total_time = sum(lap_times)
    sequence = tuple(sorted(compound for compound, laps in strategy))
    
    if sequence not in best_by_sequence or total_time < best_by_sequence[sequence]["TotalTime"]:
        best_by_sequence[sequence] = {
           "Strategy": " → ".join(f"{compound} ({laps})" for compound, laps in strategy),
            "TotalTime": total_time,
            "Stints": strategy, 
        }

strategy_results = sorted(best_by_sequence.values(), key=lambda result: result["TotalTime"])

st.write(f"Simulated strategies: {len(strategy_results)}")
best_time = strategy_results[0]["TotalTime"]
st.dataframe([
    {
        "Strategy": result["Strategy"],
        "Total Time": format_time(result["TotalTime"]),
         "Delta": f"+{result['TotalTime'] - best_time:.3f} s",
    } for result in strategy_results[:10]
], hide_index= True)

st.subheader("Tyre strategy comparison")

fig = strategy_bar_chart(strategy_results[:10])
st.plotly_chart(fig, use_container_width= True)

st.subheader("Driver comparison - Green flag")
rival_options = []
for driver in driver_offsets["Driver"].tolist():
    if driver != selected_driver:
        rival_options.append(driver)

if not rival_options: 
    st.warning("You need another driver with clean laps")
    st.stop()
    
rival_driver = st.selectbox("Select the rival driver", rival_options)

initial_gap = st.number_input("Initial gap (s)", min_value = 0.0, value = 2.0, step = 0.1)

position = st.radio(f"Starting position of {selected_driver}", ["Ahead", "Behind"], horizontal = True)

rival_row = driver_offsets[driver_offsets["Driver"] == rival_driver].iloc[0]
rival_offset = rival_row["PaceOffset"]
rival_base_pace = base_pace + rival_offset

#Using the fastest strategy for both drivers
if not strategy_results: 
    st.warning("No valied strategies available for comparison")
    st.stop()
    
labels = [result["Strategy"] for result in strategy_results]
stints_by_label = {result["Strategy"]: result["Stints"] for result in strategy_results}

own_label = st.selectbox(f"{selected_driver} strategy", labels, index=0)
rival_label = st.selectbox(f"{rival_driver} strategy", labels, index=0)

selected_lap_times = simulate_strategy(
    stints_by_label[own_label],
    driver_base_pace,
    compound_params,
    pit_loss,
    knee_ages=knee_ages,
    cliff_slope=cliff_slope,
)

rival_lap_times = simulate_strategy(
    stints_by_label[rival_label],
    rival_base_pace,
    compound_params,
    pit_loss,
    knee_ages=knee_ages,
    cliff_slope=cliff_slope,
)

if position == "Ahead":
    lead = initial_gap
else: 
    lead = -initial_gap
    
gap_by_lap = [lead]

for selected_time, rival_time in zip(selected_lap_times, rival_lap_times):
    lead += rival_time - selected_time
    gap_by_lap.append(lead)

gap_table = pd.DataFrame({"Lap": range(len(gap_by_lap)), 
                          f"{selected_driver} lead(s)": gap_by_lap}
                         )

st.line_chart(gap_table.set_index("Lap"))

if lead > 0:
    st.metric(
        "Gap at the finish",
        f"{selected_driver} ahead by {lead:.3f} s",
    )
elif lead < 0:
    st.metric(
        "Gap at the finish",
        f"{rival_driver} ahead by {abs(lead):.3f} s",
    )
else:
    st.metric("Gap at the finish", "Equal")

