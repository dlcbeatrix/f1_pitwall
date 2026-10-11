import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.calibration import (
    find_session_sources,
    RACE_CODE,
    RACES,
    estimate_pit_loss,
    calibrate_tyre_degradation,
    build_degradation_model,
    DRY_COMPOUNDS,
    TYRE_OFFSET,
    estimate_driver_pace_offset,
    FUEL_EFFECT,
    empirical_degradation_curve,
    estimate_neutralised_pit_cost,
)
from src.ui import (
    race_selector,
    get_laps,
    show_sessions_status,
    format_time,
    strategy_bar_chart,
    format_race_time,
    custom_strategy_picker,
)
from src.strategy import simulate_strategy, generate_strategies
from src.data import COMPOUND_COLORS, DEFAULT_COLOR, team_color_map

st.title("Race Strategy Predictor")

label, event_name = race_selector(RACES)
sources = find_session_sources(event_name)

if sources.race_year is None or sources.practice_year is None:
    st.warning("No saved practice or race data found for this circuit")
    st.stop()

sessions = [(sources.race_year, sources.race_round, RACE_CODE)]
for code in sources.practice_sessions:
    sessions.append((sources.practice_year, sources.practice_round, code))

st.subheader(f"Data used for {label}: {sources.race_year} race · "
    f"practice {sources.practice_year} ({', '.join(sources.practice_sessions)})")
show_sessions_status(sessions, quiet=True)

toast_key = f"data_toast_{label}"
if toast_key not in st.session_state:
    st.toast("Session data loaded", icon=":material/check_circle:")
    st.session_state[toast_key] = True

race_laps = get_laps(sources.race_year, sources.race_round, RACE_CODE)

team_colors = team_color_map(race_laps)
driver_teams = (
    race_laps[["Driver", "Team"]]
    .dropna()
    .drop_duplicates("Driver")
    .set_index("Driver")["Team"]
    .to_dict()
)

driver_colors = {
    driver: team_colors.get(team, DEFAULT_COLOR)
    for driver, team in driver_teams.items()
}

practice_laps = {}
for code in sources.practice_sessions:
    practice_laps[code] = get_laps(sources.practice_year, sources.practice_round, code)

pit_loss, pit_stops, pit_skipped = estimate_pit_loss(race_laps)
neutral_stops = estimate_neutralised_pit_cost(race_laps)

practice_calibration = calibrate_tyre_degradation(practice_laps, fuel_effect=0.0)
race_calibration = calibrate_tyre_degradation({RACE_CODE: race_laps}, FUEL_EFFECT)


degradation_model = build_degradation_model(practice_calibration, race_calibration)

medium = race_calibration[race_calibration["Compound"] == "MEDIUM"]
if medium.empty or pd.isna(pit_loss):
    st.warning("Missing Medium race data or pit loss: cannot simulate")
    st.stop()
base_pace = medium["BasePace"].iloc[0]

total_laps = int(race_laps["LapNumber"].max())

# Estimate typical tyre life limits from the race data

tyre_laps = race_laps[
    race_laps["Compound"].isin(DRY_COMPOUNDS) & race_laps["TyreLife"].notna()
]
stint_max_ages = (
    (tyre_laps.groupby(["Driver", "Stint", "Compound"])["TyreLife"])
    .max()
    .reset_index(name="MaxTyreLife")
)
driver_max_ages = (
    (stint_max_ages.groupby(["Driver", "Compound"])["MaxTyreLife"])
    .max()
    .reset_index(name="LongestStint")
)

compound_limits = (
    driver_max_ages.groupby("Compound")["LongestStint"].median().round().astype(int)
)

pit_windows = {}

for compound, typical_max in compound_limits.items():
    if typical_max < 8:
        pit_windows[compound] = None
    else:
        pit_windows[compound] = (max(8, int(typical_max) - 3), int(typical_max) + 3)

degradation_by_compound = dict(
    zip(degradation_model["Compound"], degradation_model["Degradation"])
)
source_by_compound = dict(
    zip(degradation_model["Compound"], degradation_model["Source"])
)

# Model assumptions live in the sidebar
with st.sidebar.expander("Tyre assumptions", expanded=False):
    compound_params = {}

    for compound in DRY_COMPOUNDS:
        default_degradation = float(degradation_by_compound.get(compound, 0.05))
        degradation = st.slider(
            f"{compound.title()} degradation (s/lap)",
            0.0,
            0.15,
            default_degradation,
            0.005,
            key=f"deg_{compound}",
        )

        if compound == "MEDIUM":
            offset = 0.0
        else:
            offset = st.slider(
                f"{compound.title()} pace vs Medium (s/lap)",
                -1.0,
                1.0,
                float(TYRE_OFFSET[label][compound]),
                0.05,
                key=f"offset_{compound}",
            )

        compound_params[compound] = {"offset": offset, "degradation": degradation}

with st.sidebar.expander("Pace offset method", expanded=False):
    offset_compound = st.selectbox(
        "Laps used for pace offset",
        ["All compounds", "HARD", "MEDIUM", "SOFT"],
        key="offset_compound",
    )
    offset_statistic = st.selectbox(
        "Statistic", ["median", "mean"], key="offset_statistic"
    )

only_compound = None if offset_compound == "All compounds" else offset_compound

driver_offsets = estimate_driver_pace_offset(
    race_laps,
    base_pace,
    compound_params,
    FUEL_EFFECT,
    only_compound=only_compound,
    statistic=offset_statistic,
)

if driver_offsets.empty:
    st.warning("No clean laps available to estimate driver pace")
    st.stop()

with st.sidebar.expander("Maximum stint length", expanded=False):
    max_stint_laps = {}

    for compound in DRY_COMPOUNDS:
        window = pit_windows.get(compound)
        default_max = window[1] if window is not None else 20
        default_max = max(8, min(default_max, total_laps))
        max_stint_laps[compound] = st.slider(
            f"{compound.title()} max stint(laps)",
            8,
            total_laps,
            default_max,
            1,
            key=f"max_stint{compound}",
        )

with st.sidebar.expander("Tyre cliff", expanded=False):
    knee_ages = {}
    for compound in DRY_COMPOUNDS:
        typical = (
            int(compound_limits[compound]) if compound in compound_limits.index else 15
        )
        typical = max(5, min(typical, total_laps))

        knee_ages[compound] = st.slider(
            f"{compound.title()} cliff age (laps)",
            5,
            total_laps,
            typical,
            1,
            key=f"cliff_age_{compound}",
        )

    cliff_slope = st.slider(
        "Extra wear after the cliff (s/lap per lap)",
        0.0,
        0.3,
        0.0,
        0.01,
        key="cliff_slope",
    )

#Pace based on driver
driver_options = driver_offsets["Driver"].tolist()
if len(driver_options) < 2:
    st.warning("At least two drivers with clean laps are required.")
    st.stop()
    
selected_driver = st.selectbox("Your driver", driver_options, key="selected_driver")
selected_row = driver_offsets[driver_offsets["Driver"] == selected_driver].iloc[0]

driver_offset = selected_row["PaceOffset"]
driver_base_pace = base_pace + driver_offset
selected_color = driver_colors.get(selected_driver, DEFAULT_COLOR)

# Rank strategies under green-flag conditions
strategies = generate_strategies(DRY_COMPOUNDS, total_laps, 2)


strategies = [
    strategy
    for strategy in strategies
    if all(laps <= max_stint_laps[compound] for compound, laps in strategy)
]


best_by_sequence = {}


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

    if (
        sequence not in best_by_sequence
        or total_time < best_by_sequence[sequence]["TotalTime"]
    ):
        best_by_sequence[sequence] = {
            "Strategy": " → ".join(
                f"{compound} ({laps})" for compound, laps in strategy
            ),
            "TotalTime": total_time,
            "Stints": strategy,
        }

strategy_results = sorted(
    best_by_sequence.values(), key=lambda result: result["TotalTime"]
)
if not strategy_results:
    st.warning("No valied strategies available for comparison")
    st.stop()
    
tab_rank, tab_h2h, tab_details = st.tabs(
    ["Recommended strategies", "Head-to-head", "Model details"]
)
with tab_rank: 
    window_table = pd.DataFrame(
        [
            {
                "Compound": compound,
                "Typical max tyre age": int(compound_limits[compound]),
                "Pit window": (
                    "Insufficient data"
                    if pit_windows[compound] is None
                    else f"{pit_windows[compound][0]}–{pit_windows[compound][1]} laps"
                ),
            }
            for compound in compound_limits.index
        ]
    )
    st.subheader("Stint duration estimated from the race")
    st.dataframe(window_table, hide_index=True)
    
    st.caption(
        f"{label} · {sources.race_year} · " f"{total_laps} race laps · Green-flag ranking" f" for {selected_driver}"
    )
    st.write(f"Simulated strategies: {len(strategy_results)}")

    best_time = strategy_results[0]["TotalTime"]

    strategy_table = [
        {
            "Strategy": result["Strategy"],
            "Total Time": format_race_time(result["TotalTime"]),
            "Delta": f"+{result['TotalTime'] - best_time:.3f} s",
        }
        for result in strategy_results[:10]
    ]

    table_col, chart_col = st.columns([1, 1])

    with table_col:
        st.dataframe(strategy_table, hide_index=True, use_container_width=True)

    with chart_col:
        fig = strategy_bar_chart(strategy_results[:10])
        st.plotly_chart(fig, use_container_width=True)
        
    st.metric(f"{selected_driver} pace vs field", f"{driver_offset:+.3f} s/lap")

# Pit loss estimates
green_col, neutral_col = st.columns(2)

with green_col:
    if pd.isna(pit_loss):
        st.metric("Pit stop loss with green flag", "n/a")
    else:
        st.metric("Pit stop loss with green flag", f"{pit_loss:.1f} s")
    st.caption(f"Median over {len(pit_stops)} green-flag pit-stops")

with neutral_col:
    if neutral_stops.empty:
        st.metric("Pit stop loss under VSC/SC", "n/a")
    else:
        st.metric(
            "Pit stop loss under VSC/SC", f"{neutral_stops['Cost'].median():.1f} s"
        )
    st.caption(f"Median over {len(neutral_stops)} stops under VSC/SC")

with tab_details:
    st.subheader("Tyre wear curve")
    st.caption(
        "This section is still under construction: the tyre cliff is not detected automatically. "
        "Read on the curve the tyre age where the time lost starts to rise faster, and by how much, "
        "then set those values with the cliff sliders in the sidebar."
    )

    include_practice = st.checkbox("Include practice sessions (noisy)", value=False)
    curve_laps_by_session = {RACE_CODE: race_laps}
    fuel_effect_by_session = {RACE_CODE: FUEL_EFFECT}
    if include_practice:
        for code, laps in practice_laps.items():
            curve_laps_by_session[code] = laps
            fuel_effect_by_session[code] = 0.0

    curve = empirical_degradation_curve(
        curve_laps_by_session,
        fuel_effect_by_session,
        min_stint_laps=6,
        min_stints_per_age=5,
    )
    if curve.empty:
        st.info("Not enough stints to draw the wear curve")
    else:
        fig = px.line(
            curve,
            x="TyreLife",
            y="MedianTimeLost",
            color="Compound",
            line_dash="Session",
            markers=True,
            hover_data=["Stints"],
            color_discrete_map=COMPOUND_COLORS,
            labels={
                "TyreLife": "Tyre age (laps)",
                "MedianTimeLost": "Time lost vs start of stint (s)",
                "Session": "Session",
                "Stints": "Indipendent stints",
            },
        )
        st.plotly_chart(fig)

with tab_h2h:
    st.header("Head-to-head comparison")
    st.caption(
        "Preliminary estimate: pace offsets are based on observed race laps and may "
        "include car performance, tyre choice and race conditions. The comparison "
        "assumes green-flag running and does not model traffic or safety cars."
    )
    rival_options = [driver for driver in driver_options if driver != selected_driver]

    rival_col, gap_col, position_col = st.columns([1, 0.8, 0.9])

    with rival_col:
        rival_driver = st.selectbox(
            "Rival driver",
            rival_options,
        )

    with gap_col:
        initial_gap = st.number_input(
            "Initial gap (s)",
            min_value=0.0,
            value=2.0,
            step=0.1,
        )

    with position_col:
        position = st.radio(
            f"{selected_driver} starts",
            ["Ahead", "Behind"],
        )


    rival_color = driver_colors.get(rival_driver, DEFAULT_COLOR)
    rival_row = driver_offsets[driver_offsets["Driver"] == rival_driver].iloc[0]
    rival_offset = rival_row["PaceOffset"]
    rival_base_pace = base_pace + rival_offset

    st.markdown(
        f"<h3><span style='color:{selected_color}'>"
        f"{selected_driver}</span> vs "
        f"<span style='color:{rival_color}'>"
        f"{rival_driver}</span></h3>",
        unsafe_allow_html=True,
    )

    with st.expander("Driver pace offsets", expanded=False):
        pace_col, rival_pace_col = st.columns(2)

        with pace_col:
            st.metric(
                f"{selected_driver} pace offset",
                f"{selected_row['PaceOffset']:+.3f} s/lap",
            )

        with rival_pace_col:
            st.metric(
                f"{rival_driver} pace offset",
                f"{rival_row['PaceOffset']:+.3f} s/lap",
            )
        display_offsets = driver_offsets.copy()
        display_offsets["PaceOffset"] = display_offsets["PaceOffset"].apply(
            lambda value: f"{value:+.3f} s/lap"
        )
        st.dataframe(display_offsets, hide_index=True)

    labels = [result["Strategy"] for result in strategy_results]
    stints_by_label = {result["Strategy"]: result["Stints"] for result in strategy_results}

    use_custom = st.checkbox("Custom strategies(replay a real race)")

    own_col, rival_strategy_col = st.columns(2)

    if use_custom:
        with own_col:
            own_stints = custom_strategy_picker(
                selected_driver, total_laps, DRY_COMPOUNDS, "own", 1, 14
            )
        with rival_strategy_col:
            rival_stints = custom_strategy_picker(
                rival_driver, total_laps, DRY_COMPOUNDS, "rival", 0, 14
            )
    else:
        with own_col:
            own_label = st.selectbox(f"{selected_driver} strategy", labels, index=0)

        with rival_strategy_col:
            rival_label = st.selectbox(f"{rival_driver} strategy", labels, index=0)
        own_stints = stints_by_label[own_label]
        rival_stints = stints_by_label[rival_label]

    pit_own_col, pit_rival_col = st.columns(2)
    with pit_own_col:
        own_pit_loss = st.number_input(
            f"{selected_driver} pit loss (s)",
            min_value=0.0,
            value=float(pit_loss),
            step=0.5,
            key="own_pit_loss",
        )
    with pit_rival_col:
        rival_pit_loss = st.number_input(
            f"{rival_driver} pit loss (s)",
            min_value=0.0,
            value=float(pit_loss),
            step=0.5,
            key="rival_pit_loss",
        )

    with st.expander("VSC/SC Scenario"):
        use_neutral = st.checkbox("A VSC/SC happens in the race", key="use_neutral")
        neutral_window = None
        neutral_cost = None
        if use_neutral:
            neutral_start = st.number_input(
                "First lap with VSC/SC",
                min_value=1,
                max_value=total_laps,
                value=14,
                step=1,
                key="neutral_start",
            )
            neutral_end = st.number_input(
                "Last lap with VSC/SC",
                min_value=1,
                max_value=total_laps,
                value=14,
                step=1,
                key="neutral_end",
            )
            default_cost = (
                float(neutral_stops["Cost"].median()) if not neutral_stops.empty else 10.0
            )
            neutral_cost = st.number_input(
                "Pit loss under VSC/SC (s)",
                min_value=0.0,
                max_value=40.0,
                value=default_cost,
                step=0.5,
                key="neutral_cost",
            )
            neutral_window = (neutral_start, neutral_end)

    st.caption(
        "Driver pace offsets come from observed race laps and may reflect "
        "car performance and race conditions. The VSC/SC scenario changes "
        "pit loss only; traffic, overtaking and pace under neutralisation "
        "are not modelled."
    )

    start_lap = st.number_input(
        "Start the comparison at lap",
        min_value=0,
        max_value=total_laps - 1,
        value=0,
        step=1,
    )


    selected_lap_times = simulate_strategy(
        own_stints,
        driver_base_pace,
        compound_params,
        own_pit_loss,
        knee_ages=knee_ages,
        cliff_slope=cliff_slope,
        neutral_laps=neutral_window,
        neutral_pit_loss=neutral_cost,
    )

    rival_lap_times = simulate_strategy(
        rival_stints,
        rival_base_pace,
        compound_params,
        rival_pit_loss,
        knee_ages=knee_ages,
        cliff_slope=cliff_slope,
        neutral_laps=neutral_window,
        neutral_pit_loss=neutral_cost,
    )
    lead = initial_gap if position == "Ahead" else -initial_gap
    gap_by_lap = [lead]

    for selected_time, rival_time in zip(
        selected_lap_times[start_lap:], rival_lap_times[start_lap:]
    ):
        lead += rival_time - selected_time
        gap_by_lap.append(lead)

    gap_table = pd.DataFrame(
        {
            "Lap": range(start_lap, start_lap + len(gap_by_lap)),
            f"{selected_driver} lead(s)": gap_by_lap,
        }
    )
    st.subheader("Projected race gap")
    chart_col, result_col = st.columns([3, 1])
    with chart_col:
        gap_fig = px.line(
            gap_table,
            x="Lap",
            y=f"{selected_driver} lead(s)",
            labels={
                "Lap": "Lap",
                f"{selected_driver} lead(s)": "Gap to rival (s)",
            },
        )
        gap_fig.update_traces(
            line_color=selected_color,
            line_width=3,
            name=f"{selected_driver} lead",
        )
        gap_fig.add_hline(
            y=0,
            line_dash="dash",
            line_color="#7D8794",
        )
        gap_fig.update_layout(
            height=430,
            margin=dict(l=10, r=10, t=20, b=10),
            showlegend=False,
        )
        
        if neutral_window is not None:
            gap_fig.add_vrect(
                x0=neutral_window[0] - 0.5,
                x1=neutral_window[1] + 0.5,
                fillcolor="#F5C400",
                opacity=0.15,
                line_width=0,
                annotation_text="VSC/SC",
        )
        
        st.plotly_chart(gap_fig, use_container_width=True)

    with result_col:
        st.metric("Gap at the finish", f"{abs(lead):.3f} s")

        if lead > 0:
            st.caption(f"{selected_driver} ahead")
        elif lead < 0:
            st.caption(
                f"{rival_driver} ahead",
            )
        else:
            st.caption("Equal")

    with st.expander("Real race vs simulation", expanded=False):
        if "Time" not in race_laps.columns:
            st.info(
                "This race file has no lap timestamps, so the backtest "
                "cannot be displayed."
            )
        else:
            own_real = race_laps[race_laps["Driver"] == selected_driver][
                ["LapNumber", "Time"]
            ]
            rival_real = race_laps[race_laps["Driver"] == rival_driver][
                ["LapNumber", "Time"]
            ]

            real = own_real.merge(
                rival_real,
                on="LapNumber",
                suffixes=("_own", "_rival"),
            )
            real["Real"] = (real["Time_rival"] - real["Time_own"]).dt.total_seconds()

            sim = gap_table.rename(
                columns={
                    "Lap": "LapNumber",
                    f"{selected_driver} lead(s)": "Simulated",
                }
            )
            compare = sim.merge(
                real[["LapNumber", "Real"]],
                on="LapNumber",
                how="left",
            )

            backtest_fig = go.Figure()
            backtest_fig.add_trace(
                go.Scatter(
                    x=compare["LapNumber"],
                    y=compare["Real"],
                    mode="lines",
                    name="Real",
                    line=dict(color="#AAB3C0", dash="dot"),
                )
            )
            backtest_fig.add_trace(
                go.Scatter(
                    x=compare["LapNumber"],
                    y=compare["Simulated"],
                    mode="lines",
                    name="Simulated",
                    line=dict(color=selected_color, width=3),
                )
            )
            backtest_fig.add_hline(
                y=0,
                line_dash="dash",
                line_color="#7D8794",
            )
            backtest_fig.update_layout(
                xaxis_title="Lap",
                yaxis_title="Selected driver lead(s)",
                height=430,
                margin=dict(l=10, r=10, t=20, b=10),
                legend=dict(orientation="h", y=1.08),
            )
            st.plotly_chart(backtest_fig, use_container_width=True)

            if st.checkbox("Show lap-by-lap data", key="show_lap_data"):
                st.dataframe(compare, hide_index=True)


# ---------------------
with tab_details:
    st.subheader("Degradation by compound")
    display_deg = degradation_model.copy()
    display_deg["Degradation"] = display_deg["Degradation"].apply(
        lambda value: f"{value:+.3f} s/lap"
    )
    st.dataframe(display_deg, hide_index=True)

    with st.expander("Calibration details"):
        display_fp = practice_calibration.copy()
        display_fp["BasePace"] = display_fp["BasePace"].apply(format_time)
        display_fp["Degradation"] = display_fp["Degradation"].apply(
            lambda d: f"{d:+.3f} s/lap"
        )
        st.write("Tyre degradation during FP:")
        st.dataframe(display_fp, hide_index=True)

        display_race = race_calibration.copy()
        display_race["BasePace"] = display_race["BasePace"].apply(format_time)
        display_race["Degradation"] = display_race["Degradation"].apply(
            lambda d: f"{d:+.3f} s/lap"
        )
        st.write("Tyre degradation during the Race:")
        st.dataframe(display_race, hide_index=True)
