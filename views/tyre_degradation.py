import streamlit as st
import plotly.express as px

from src.data import (DEFAULT_COLOR, TYRE_SESSIONS, SESSION_LABELS, team_color_map)
from src.tyres import clean_laps, tyres_degradation
from src.ui import (format_time, get_laps, session_selector)


COMPOUND_COLORS = {
    "SOFT": "#e10600", "MEDIUM": "#f5c400", "HARD": "#888888",
    "INTERMEDIATE": "#43b02a", "WET": "#0067ad",
}


st.title('Tyre Degradation Analysis')

year, rnd, gp_name, code = session_selector(TYRE_SESSIONS)
laps = get_laps(year, rnd, code)
colors = team_color_map(laps)
title = f"{gp_name} {year} - {SESSION_LABELS[code]}"

driver = st.sidebar.selectbox("Driver", sorted(laps["Driver"].unique()), index= None, placeholder= "Select a driver")
if driver is None:
    st.info("Select a driver in the sidebar.")
    st.stop()
    
fuel_k = st.sidebar.slider("Fuel effect (s/lap)", 0.0, 0.08, 0.05, 0.005, label_visibility= "visible")
minimum_stint_length = st.sidebar.slider("Minimum stint length:", min_value = 6, max_value = 45, value = 10, step = 1, label_visibility= "visible")

race_laps = clean_laps(laps, driver, fuel_k, minimum_stint_length)
if race_laps.empty: 
    st.warning('No valid laps for this driver. Try lowering the minimum stint length.')
    st.stop()
    
team = race_laps["Team"].iloc[0]
team_color = colors.get(team, DEFAULT_COLOR)

st.markdown(f"<h3 style='border-left: 8px solid {team_color}; padding-left: 12px'>"
    f"{driver} · {team} — {title}</h3>",
    unsafe_allow_html=True,)

summary = tyres_degradation(race_laps)
if summary.empty: 
    st.info("Not enough laps to estimate the degradation")
else: 
    metric_columns = st.columns(len(summary))
    for i in range(len(summary)):
        row = summary.iloc[i]
        metric_columns[i].metric( label=f"Stint {int(row['Stint'])} - {row['Compound']} - {int(row['Laps'])} laps",
            value=f"{row['Degradation']:+.3f} s/lap",
        )
    st.caption("Slope of a straight line fitted to the fuel-corrected lap times of each stint. "
               "Positive = the tyre gets slower lap after lap.")

fig = px.scatter(race_laps, x = "LapNumber", y="LapTimeCorrect", color = "Compound",
                 hover_data=["Stint", "TyreLife"],
                 color_discrete_map=COMPOUND_COLORS,
                 labels={"LapNumber": "Lap", "LapTimeCorrect": "Fuel-corrected lap time(s)"})

fig.update_traces(marker=dict(size = 12, line=dict(width=1.5, color=team_color)))

#Regression line of each stint, drawn on top of the points
for i in range(len(summary)):
    row = summary.iloc[i]
    stint_laps = race_laps[race_laps["Stint"] == row["Stint"]]
    
    x_start = stint_laps["LapNumber"].min()
    x_end = stint_laps["LapNumber"].max()
    
    y_start = row["Degradation"] * x_start + row["Intercept"]
    y_end = row["Degradation"] * x_end + row["Intercept"]
    
    fig.add_scatter(
        x = [x_start, x_end], y = [y_start, y_end],
        mode = 'lines', 
        line = dict(color = "white", width = 3, dash = "dash"), showlegend= False, 
        hoverinfo= "skip"
    )

fig.update_layout(height=650)
st.plotly_chart(fig)

table = race_laps[["LapNumber", "Stint", "Compound", "TyreLife", "LapTimeSec", "LapTimeCorrect"]].copy()
for column in ["LapNumber", "TyreLife"]:
    table[column] = table[column].astype("Int64")

table["Lap time"] = table["LapTimeSec"].apply(format_time)
table["Corrected"] = table["LapTimeCorrect"].apply(format_time)
table = table[["LapNumber", "Compound", "TyreLife", "Lap time", "Corrected"]]

def color_row(row):
    background = COMPOUND_COLORS.get(row["Compound"], "#444444")
    text = "white" if row["Compound"] in ("SOFT", "WET") else "black"
    return [f"background-color: {background}; color: {text}"] * len(row)

st.dataframe(table.style.apply(color_row, axis=1), hide_index=True)