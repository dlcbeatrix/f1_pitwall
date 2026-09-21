import numpy as np
import plotly.graph_objects as grob
import streamlit as st
import pandas as pd

from src.data import (DEFAULT_COLOR, SESSION_CODES, SESSION_LABELS, team_color_map)
from src.ui import (get_laps, get_speed, session_selector, format_time)
from src.radio import (dequantize, quantize, from_bits, to_bits, map_pam, demap_pam, gray_pam_table,
                       add_noise, decide_pam, theoretical_ser)

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
    
#SIDEBAR 
show_theory = st.sidebar.checkbox("Show theory notes", value = True)
bits = st.sidebar.slider("Quantization bits", 2, 12, 8)
k = st.sidebar.slider("Bits per symbol (k)", 1, 4, 2)
ebn0_db = st.sidebar.slider("Eb/N0 (dB)", -5.0, 25.0, 10.0, 0.5)


trace = get_speed(year, rnd, code, driver)
t = trace["Time"].to_numpy() #time (s)
x_t = trace["Speed"].to_numpy() #speed (km/h)

team = laps[laps["Driver"] == driver]["Team"].iloc[0]
team_color = colors.get(team, DEFAULT_COLOR)

st.markdown(f"<h3 style='border-left: 8px solid {team_color}; padding-left: 12px'>"
    f"{driver} · {team} · {gp_name} {year} - {SESSION_LABELS[code]} · fastest lap</h3>",
    unsafe_allow_html=True,)

#1. Sampling
st.subheader("1. Sampling")

if show_theory: 
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

#2. Quantization
st.subheader("2. Quantization")

if show_theory:
    st.info("**Theory: quantization**")
    st.markdown(r"""
    Quantization turns each real-valued sample $x[n]$ into one of $L = 2^b$ integer levels,
    so that it can be written with $b$ bits:
    $$
    q[n] = \operatorname{round}\left( \frac{x[n] - x_{min}}{x_{max} - x_{min}} \, (L - 1) \right)
    $$
    The distance between two adjacent levels is the **quantization step**:
    $$
    \Delta = \frac{x_{max} - x_{min}}{L - 1}
    $$
    The receiver rebuilds the signal as $\hat{x}[n] = x_{min} + q[n]\,\Delta$, and the difference
    $e[n] = x[n] - \hat{x}[n]$ is the **quantization error**. It always satisfies
    $|e[n]| \le \Delta/2$ and, if $\Delta$ is small compared to the variations of the signal,
    it is approximately uniform in $[-\Delta/2, \Delta/2]$. Its mean square value is then
    $$
    \text{MSE} = E\{e^2[n]\} = \frac{\Delta^2}{12}
    $$
    This is the value shown in the caption below, to compare with the measured MSE.

    * Each extra bit halves $\Delta$, so the MSE becomes 4 times smaller: about
      **6 dB more SQNR per bit** ($10 \log_{10} 4 \approx 6.02$ dB).
    * The price is a higher bit rate: $R_b = b \cdot f_s$ bit/s.
    * Assumption: the receiver knows $x_{min}$ and $x_{max}$.
    """)

q, x_min, x_max = quantize(x_t, bits)
x_rec = dequantize(q, bits, x_min, x_max)

step = (x_max-x_min)/(2**bits-1)
mse = np.mean((x_t - x_rec)**2)

col1, col2, col3 = st.columns(3)
col1.metric("Levels", 2**bits)
col2.metric("Step (Δ)", f"{step:.3f} km/h")
col3.metric("MSE", f"{mse:.4f} (km/h)²")
st.caption(f"Theory for a uniform quantizer: Δ²/12 = {step ** 2 / 12:.4f} (km/h)²")

fig_q = grob.Figure()

fig_q.add_trace(grob.Scatter(x=t, y=x_t, mode="lines", name="Original",
                           line=dict(color="#00d26a", width=2)))
fig_q.add_trace(grob.Scatter(x=t, y=x_rec, mode="lines", name="Quantized",
                           line=dict(color="#ca00e1", width=2), opacity=0.5))


fig_q.update_layout(xaxis_title = "Time(s)", yaxis_title = "Speed (km/h)", height = 600)
st.plotly_chart(fig_q)

#3. Bit Coding and PAM Mapping
st.subheader("3. Bit coding and PAM mapping")

if show_theory:
    st.info("**Theory: bit coding and M-PAM mapping**")
    st.markdown(r"""
    Each quantization level is written with $b$ bits (binary coding), giving a bit rate
    $R_b = b\, f_s$. The bits are grouped $k$ at a time and each group is mapped to one
    amplitude of an **M-PAM** constellation, with $M = 2^k$:
    $$
    a_i \in \{ \pm 1, \pm 3, \dots, \pm (M-1) \}
    $$
    The symbol rate is $R_s = R_b / k$, so a larger $k$ needs fewer symbols per second
    (less bandwidth) but the amplitudes are closer together, hence more errors at the same noise.
    The average symbol energy (with unit spacing $d=1$) is
    $$
    E_s = \frac{M^2 - 1}{3}
    $$
    With **Gray mapping** neighbouring amplitudes differ by only one bit: when the noise
    makes the decision fall on a neighbouring amplitude (the most likely error), only one bit is wrong.
    """)
    
bit_stream = to_bits(q, bits)
symbols, n_padding = map_pam(bit_stream, k)

#No noise test
bits_back = demap_pam(symbols, k, n_padding)
q_back = from_bits(bits_back, bits)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Bits to send", len(bit_stream))
col2.metric("Levels of the PAM (M)", 2 ** k)
col3.metric("Symbols", len(symbols))
col4.metric("Bit errors (no noise)", int(np.sum(bit_stream != bits_back)))
st.caption(f"Padding bits: {n_padding}. Levels recovered exactly: {np.array_equal(q, q_back)}")

table = gray_pam_table(k)
rows = []
for label in range(2**k):
    rows.append({"Bits": format(label, f"0{k}b"), "Amplitude": table[label]})

mapping = pd.DataFrame(rows).sort_values("Amplitude")
st.write("Gray mapping table: ")
st.dataframe(mapping, hide_index = True)

#4. Noisy channel, decision and reconstruction
st.subheader("4. Noisy channel and reconstruction")

if show_theory:
    st.info("**Theory: AWGN channel and decision**")
    st.markdown(r"""
    The channel does not distort ($c(t) = \delta(t)$) but adds white Gaussian noise $w(t)$.
    After the matched filter and sampling at $kT$ (no intersymbol interference), each
    received sample is
    $$
    r[k] = a[k] + w[k], \qquad w[k] \sim \mathcal{N}\left(0, \tfrac{N_0}{2}\right)
    $$
    The noise level is set through $E_b/N_0$. Since $E_s = k\,E_b$, we have
    $E_s/N_0 = k\,E_b/N_0$. The decision is **minimum distance**: each $r[k]$ is
    assigned to the nearest amplitude. The theoretical symbol error rate of M-PAM is
    $$
    P_s = 2\left(1 - \frac{1}{M}\right) Q\left( \sqrt{\frac{6\,E_s}{(M^2 - 1)\,N_0}} \right)
    $$
    With Gray mapping, at high $E_b/N_0$ a symbol error is almost always a wrong neighbour,
    so $\text{BER} \approx P_s / k$.
    """)

received = add_noise(symbols, k, ebn0_db)
decided = decide_pam(received, k)
bits_rx = demap_pam(received, k, n_padding)
q_rx = from_bits(bits_rx, bits)
x_rx = dequantize(q_rx, bits, x_min, x_max)

ser = np.mean(decided != symbols)
ber = np.mean(bits_rx != bit_stream)
mse_total = np.mean((x_t-x_rx)**2)

col1, col2, col3, col4 = st.columns(4)
col1.metric("SER (simulated): ", f"{ser:.2e}")
col2.metric("BER (simulated):", f"{ber:.2e}")
col3.metric("Final MSE", f"{mse_total:.3f} (km/h)^2")
col4.metric("Final RMSE", f"{np.sqrt(mse_total):.2f} km/h")

st.caption(f"Theoretical SER: {theoretical_ser(k, ebn0_db):.2e}. "
           f"Symbols sent: {len(symbols)}, symbol errors: {int(np.sum(decided != symbols))}. "
           f"MSE due to quantization alone: {mse:.4f} (km/h)^2")

fig_r = grob.Figure()
fig_r.add_trace(grob.Scatter(x = t, y = x_t, mode = 'lines', name = "Original", line = dict(color="#00d26a", width=2)))
fig_r.add_trace(grob.Scatter(x = t, y = x_rx, mode = 'lines', name = 'Received',line=dict(color="#d900e1", width=2), opacity=0.5))
fig_r.update_layout(xaxis_title = "Time(s)", yaxis_title = "Speed (km/h)", height = 600)
st.plotly_chart(fig_r)