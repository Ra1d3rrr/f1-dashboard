import streamlit as st
import fastf1
from fastf1 import plotting
import pandas as pd
import plotly.express as px

# Enable cache for FastF1
fastf1.Cache.enable_cache('cache')

st.set_page_config(layout="wide", page_title="F1 Telemetry Dashboard")

st.title("🏁 Formula 1 Telemetry Dashboard")

# Sidebar for session selection
with st.sidebar:
    st.header("Session Selection")
    year = st.selectbox("Year", list(reversed(range(2018, 2025))), index=0)
    gp = st.text_input("Grand Prix (e.g. Monza, Bahrain)", "Monza")
    session_type = st.selectbox("Session Type", ["FP1", "FP2", "FP3", "Q", "R"])
    driver = st.text_input("Driver Code (e.g. VER, HAM, LEC)", "VER")

# Load the session
try:
    session = fastf1.get_session(year, gp, session_type)
    session.load()
except Exception as e:
    st.error(f"Failed to load session: {e}")
    st.stop()

laps = session.laps.pick_driver(driver)
if laps.empty:
    st.warning(f"No laps found for driver '{driver}' in this session.")
    st.stop()

# Display lap times
st.subheader(f"📊 Lap Times for {driver}")
lap_times = laps[["LapNumber", "LapTime", "Sector1Time", "Sector2Time", "Sector3Time", "Compound", "TyreLife"]]
st.dataframe(lap_times.set_index("LapNumber"))

# Pick fastest lap
fastest_lap = laps.pick_fastest()
st.success(f"Fastest Lap: {fastest_lap['LapTime']} on lap {fastest_lap['LapNumber']}")

# Telemetry data
st.subheader("📈 Telemetry - Speed vs Distance")
tel = fastest_lap.get_car_data().add_distance()

fig1 = px.line(
    tel,
    x='Distance',
    y='Speed',
    title=f"{driver} - Speed on Fastest Lap",
    labels={'Distance': 'Distance (m)', 'Speed': 'Speed (km/h)'},
    template="plotly_dark"
)
st.plotly_chart(fig1, use_container_width=True)

# Position map
st.subheader("🗺️ Car Position on Track (X vs Y)")
pos = fastest_lap.get_pos_data()
if pos is not None:
    fig2 = px.line(
        pos,
        x='X',
        y='Y',
        title=f"{driver} - Car Position on Fastest Lap",
        labels={'X': 'X (track position)', 'Y': 'Y (track position)'},
        template="plotly_dark"
    )
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.warning("Position data not available for this session.")