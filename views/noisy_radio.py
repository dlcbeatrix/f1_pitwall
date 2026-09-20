import numpy as np
import plotly.graph_objects as grob
import streamlit as st

from src.data import (DEFAULT_COLOR, SESSION_CODES, SESSION_LABELS, team_color_map)
from src.ui import (get_laps, get_speed, session_selector, format_time)

st.title('The Noisy Radio')
st.write('This module simulates how F1 telemetry travels from the car to the pit wall:'
         ' sampling, quantization, radio noise and reconstruction using concepts from systems of digital communications on real data.')

year, rnd, gp_name, code = session_selector(set(SESSION_CODES.values()))
laps = get_laps(year, rnd, code)
colors = team_color_map(laps)

driver = st.sidebar.selectbox("Driver", sorted(laps["Driver"].unique()), index = None, placeholder = "Select a driver")

if driver is None: 
    st.info('Select a driver in the sidebar')
    st.stop()
    
    
show_teory = st.sidebar.checkbox("Show theory notes", value = True)

trace = get_speed(year, rnd, code, driver)
t = trace["Time"].to_numpy() #time (s)
x_t = trace["Speed"].to_numpy() #speed (km/h)

team = laps[laps["Driver"] == driver]["Team"].iloc[0]
team_color = colors.get(team, DEFAULT_COLOR)

st.caption(f"{driver} · {team} · {gp_name} {year} - {SESSION_LABELS[code]} · fastest lap")

#1. Sampling
st.subheader("1. Sampling")

if show_teory: 
    st.info("**Theory: signals and sampling**")
    st.markdown(r"""
    Here we take an analogue signal $x(t)$ (the real speed of the car) and turn it into a
    discrete-time signal $x[n]$. The mathematical operation is **ideal sampling**:
    $$
    x[n] = x(n T_s), \quad n = 0, 1, \dots, N-1
    $$
    where:
    * $T_s$ is the **sampling period** (time between two consecutive samples).
    * $f_s = 1/T_s$ is the **sampling frequency**.

    > **Nyquist-Shannon theorem:** to avoid aliasing (losing information) we need
    > $f_s > 2B$, where $B$ is the bandwidth of the speed signal.
    """)
    
fig = grob.Figure()
fig.add_trace(grob.Scatter(x=t, y = x_t, mode = 'lines', name =f"Speed {driver}",
                           line = dict(color = team_color, width = 2)))
fig.update_layout(xaxis_title = "Time (s)", yaxis_title = "Speed (km/h)", height = 600)
st.plotly_chart(fig)



dt = np.diff(t)   # time between consecutive samples

fs_real = len(x_t) / t[-1]

col1, col2, col3 = st.columns(3)
col1.metric("Samples (N)", len(x_t))
col2.metric("Lap duration (T)", f"{t[-1]:.3f} s = {format_time(t[-1])}")
col3.metric("Average sampling rate (f_s)", f"{fs_real:.2f} Hz")
st.caption(f"The interval between samples is not constant: from {dt.min() * 1000:.0f} ms "
           f"to {dt.max() * 1000:.0f} ms.")