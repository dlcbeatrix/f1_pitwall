import streamlit as st
import pandas as pd
import plotly.express as px
from src.data import ( QUALI_SESSIONS, team_color_map, DEFAULT_COLOR)
from src.ui import (session_selector, get_laps, format_time)

st.header("Qualifying Gap")

year, rnd, gp_name, code = session_selector(QUALI_SESSIONS)
laps = get_laps(year, rnd, code)
colors = team_color_map(laps)


valid_laps = laps[(laps["Deleted"] == False) & (laps["LapTime"].notna())]
if valid_laps.empty: 
    st.warning('No valid laps in this session')
    st.stop()

best_laps = valid_laps.sort_values("LapTime").drop_duplicates(subset="Driver").reset_index(drop=True)

pole_time = best_laps.loc[0, 'LapTime']
pole_driver = best_laps.loc[0, 'Driver']
best_laps['GapPole'] = (best_laps['LapTime']-pole_time).dt.total_seconds()
best_laps['FormattedTime'] = best_laps['LapTime'].dt.total_seconds().apply(format_time)

driver_order = best_laps['Driver'].tolist()

fig = px.bar(best_laps, x = "GapPole", y = "Driver", orientation = 'h',
             color = 'Team', color_discrete_map=colors, 
             category_orders={"Driver": driver_order}, 
             labels={"GapPole": "Gap to Pole (s)"},
             hover_data=['FormattedTime'],height = 650)

fig.update_xaxes(tickformat = "+.3f", dtick = 0.2, showgrid = True, griddash= 'dash')
fig.update_layout(title=f"{gp_name} {year} - Qualifying<br>"
                        f"Fastest lap: {format_time(pole_time.total_seconds())} ({pole_driver})")
st.plotly_chart(fig)


driver = st.sidebar.selectbox("Driver", sorted(laps["Driver"].unique()), index= None, placeholder= "Select a driver")        
if driver is None: 
    st.info('Select a driver to see gap ahead and behind')
    st.stop()

driver_index = best_laps.index[best_laps['Driver']== driver][0]

col1, col2, col3 = st.columns(3)

team_color = colors.get(best_laps.loc[driver_index, "Team"], DEFAULT_COLOR)
with col2: 
    st.markdown(f"<h2 style='text-align: center; color: {team_color};'>"
                f"P{driver_index + 1} - {driver}</h2><br>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align: center; font-weight: bold; color: 'white';'>"
                    f"{best_laps.loc[driver_index, 'FormattedTime']}<br>", unsafe_allow_html=True)

with col1: 
    if driver_index > 0: 
        prev_driver = best_laps.loc[driver_index-1, 'Driver']
        gap_ahead = (best_laps.loc[driver_index, 'LapTime']-best_laps.loc[driver_index-1,'LapTime']).total_seconds()
        st.markdown(f"<p style='text-align: center; font-size: 1.1rem; margin-bottom: 0;'>P{driver_index} ({prev_driver})</p>"
                    f"<h3 style='text-align: center; color: #ff4b4b; margin-top: 0;'>+ {gap_ahead:.3f} s</h3>", 
                    unsafe_allow_html=True)
        
with col3: 
    if driver_index < len(best_laps)-1:
        next_driver = best_laps.loc[driver_index+1, 'Driver']
        gap_behind = (best_laps.loc[driver_index + 1, "LapTime"] - best_laps.loc[driver_index, "LapTime"]).total_seconds()
        st.markdown(f"<p style='text-align: center; font-size: 1.1rem; margin-bottom: 0;'>P{driver_index + 2} ({next_driver})</p>"
                    f"<h3 style='text-align: center; color: #00d26a; margin-top: 0;'>- {gap_behind:.3f} s</h3>", 
                    unsafe_allow_html=True)




