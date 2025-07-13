import streamlit as st
import fastf1
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# Enable FastF1 cache
import os
os.makedirs('cache', exist_ok=True)
fastf1.Cache.enable_cache('cache')

# Auto-refresh every 10 seconds for more responsive live updates
st_autorefresh(interval=10 * 1000, key="datarefresh")

st.set_page_config(page_title="F1 Live Dashboard", layout="wide")

# Sidebar navigation
page = st.sidebar.selectbox("Select Page", ["Lap Times (Live)", "Race Results", "Driver Standings", "Constructor Standings", "Event Schedule", "Race Control"])

# Sidebar inputs
current_year = datetime.now().year
available_years = list(range(2018, current_year + 1))
available_years.reverse()  # Show newest years first
year = st.sidebar.selectbox("Year", options=available_years, index=0)

# Get race schedule for dropdown
@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_race_schedule(year):
    try:
        schedule = fastf1.get_event_schedule(year)
        if not schedule.empty:
            # Create race options with name and round number
            race_options = {}
            for _, race in schedule.iterrows():
                race_name = race.get('EventName', f'Round {race["RoundNumber"]}')
                round_num = race['RoundNumber']
                race_options[f"{race_name} ({round_num})"] = round_num
            return race_options
        return {}
    except:
        # Fallback to simple round numbers if schedule fails
        return {f"Round {i}": i for i in range(1, 24)}

race_options = get_race_schedule(year)
if race_options:
    # Default to first race if available
    default_race = list(race_options.keys())[0]
    selected_race = st.sidebar.selectbox("Select Race", options=list(race_options.keys()), index=0)
    round_number = race_options[selected_race]
else:
    # Fallback to number input if schedule loading fails
    round_number = st.sidebar.number_input("Round", min_value=1, max_value=23, value=1)

# Optimized session loading with better caching
@st.cache_data(ttl=300, show_spinner=False)  # Cache for 5 minutes, hide spinner
def load_session_fast(year, rnd, session_type='R'):
    try:
        session = fastf1.get_session(year, rnd, session_type)
        # Only load what we need for better performance
        session.load(laps=True, telemetry=False, weather=False, messages=False)
        return session
    except Exception as e:
        return None

# Load session with minimal data for basic info
@st.cache_data(ttl=120, show_spinner=False)  # Cache for 2 minutes
def load_session_minimal(year, rnd, session_type='R'):
    try:
        session = fastf1.get_session(year, rnd, session_type)
        # Load only basic session info, no lap data
        session.load(laps=False, telemetry=False, weather=False, messages=False)
        return session
    except Exception as e:
        return None

# Ultra-fast session creation - no loading until needed
def create_session_reference(year, rnd, session_type):
    """Create session reference without loading any data"""
    try:
        return fastf1.get_session(year, rnd, session_type)
    except:
        return None

# Create session references only (no data loading)
session = create_session_reference(year, round_number, 'R')
qualifying_session = create_session_reference(year, round_number, 'Q')
sprint_session = create_session_reference(year, round_number, 'S')
sprint_qualifying_session = create_session_reference(year, round_number, 'SQ')

# Get event schedule for the selected round to show dates
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_event_info(year, rnd):
    try:
        sched = fastf1.get_event_schedule(year)
        event = sched[sched['RoundNumber'] == rnd]
        if not event.empty:
            return event.iloc[0]
        return None
    except Exception as e:
        return None

event_info = get_event_info(year, round_number)

# -------- PAGE: LAP TIMES (LIVE) --------
if page == "Lap Times (Live)":
    st.title("🔴 Live Lap Times")

    # Show last updated time
    from datetime import datetime
    current_time = datetime.now().strftime("%H:%M:%S")
    st.caption(f"🕒 Last updated: {current_time} | Auto-refresh every 10 seconds")

    # Function to format lap times to milliseconds
    def format_laptime(timedelta_obj):
        if pd.isna(timedelta_obj):
            return "N/A"
        total_seconds = timedelta_obj.total_seconds()
        minutes = int(total_seconds // 60)
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:06.3f}"

    # Determine if it's a Sprint weekend
    is_sprint_weekend = sprint_session is not None or sprint_qualifying_session is not None

    # Create tabs based on weekend format
    if is_sprint_weekend:
        tab1, tab2, tab3, tab4 = st.tabs(["Race", "Qualifying", "Sprint Race", "Sprint Qualifying"])
    else:
        tab1, tab2 = st.tabs(["Race", "Qualifying"])

    with tab1:
        st.subheader("Race Session")
        if session:
            # Cached session loading for live updates (2 minute cache)
            @st.cache_data(ttl=120, show_spinner=False)
            def load_race_laps(year, rnd):
                try:
                    race_session = fastf1.get_session(year, rnd, 'R')
                    race_session.load(laps=True, telemetry=False, weather=False, messages=False)
                    return race_session.laps
                except:
                    return pd.DataFrame()

            with st.spinner("Loading race data..."):
                laps = load_race_laps(year, round_number)

            if laps.empty:
                if event_info is not None:
                    event_date = event_info.get('EventDate', 'Unknown')
                    event_name = event_info.get('EventName', 'Unknown Event')
                    st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                    st.warning("No race lap data available yet.")
                else:
                    st.warning("No race lap data available yet.")
            else:
                st.subheader("All Race Lap Times")
                # Create a copy of the dataframe with formatted lap times and sector times
                base_cols = ["Driver", "LapTime", "Compound", "TyreLife"]

                # Add sector times if available
                sector_cols = []
                if 'Sector1Time' in laps.columns:
                    sector_cols.append('Sector1Time')
                if 'Sector2Time' in laps.columns:
                    sector_cols.append('Sector2Time')
                if 'Sector3Time' in laps.columns:
                    sector_cols.append('Sector3Time')

                # Only include columns that exist
                available_cols = [col for col in base_cols if col in laps.columns] + sector_cols
                display_laps = laps[available_cols].copy()

                # Clean up driver names (remove numbers if present)
                if 'BroadcastName' in laps.columns:
                    display_laps['Driver'] = laps['BroadcastName']  # Use broadcast name instead
                elif 'LastName' in laps.columns:
                    display_laps['Driver'] = laps['LastName']  # Use last name if available

                # Format lap time
                display_laps["LapTime_Formatted"] = display_laps["LapTime"].apply(format_laptime)

                # Format sector times if available
                for sector_col in sector_cols:
                    if sector_col in display_laps.columns:
                        display_laps[f"{sector_col}_Formatted"] = display_laps[sector_col].apply(format_laptime)

                # Sort by actual lap time (race order)
                display_laps = display_laps.sort_values(by="LapTime")

                # Replace original columns with formatted ones
                display_laps = display_laps.drop("LapTime", axis=1)
                display_laps = display_laps.rename(columns={"LapTime_Formatted": "LapTime"})

                for sector_col in sector_cols:
                    if f"{sector_col}_Formatted" in display_laps.columns:
                        display_laps = display_laps.drop(sector_col, axis=1)
                        display_laps = display_laps.rename(columns={f"{sector_col}_Formatted": sector_col})

                # Reorder columns to put LapTime and sectors in the right position
                final_cols = ["Driver", "LapTime"]
                final_cols.extend([col for col in sector_cols if col in display_laps.columns])
                final_cols.extend([col for col in ["Compound", "TyreLife"] if col in display_laps.columns])
                display_laps = display_laps[final_cols]
                st.dataframe(display_laps)

                st.subheader("Fastest Race Lap Per Driver")
                # Find fastest lap per driver manually from all lap times
                if not laps.empty and 'LapTime' in laps.columns:
                    # Filter out invalid lap times (NaT, null, or extremely slow times)
                    valid_laps = laps.dropna(subset=['LapTime'])
                    valid_laps = valid_laps[valid_laps['LapTime'].notna()]

                    if not valid_laps.empty:
                        # Group by driver and find the fastest lap for each
                        fastest_per_driver = valid_laps.loc[valid_laps.groupby('Driver')['LapTime'].idxmin()]

                        # Select columns for display
                        available_cols = ["Driver", "LapTime"]
                        if "Compound" in fastest_per_driver.columns:
                            available_cols.append("Compound")

                        display_fastest = fastest_per_driver[available_cols].copy()

                        # Clean up driver names
                        if 'BroadcastName' in fastest_per_driver.columns:
                            display_fastest['Driver'] = fastest_per_driver['BroadcastName']
                        elif 'LastName' in fastest_per_driver.columns:
                            display_fastest['Driver'] = fastest_per_driver['LastName']

                        # Sort by lap time (fastest first)
                        display_fastest = display_fastest.sort_values(by="LapTime")

                        # Format the lap times
                        display_fastest["LapTime_Formatted"] = display_fastest["LapTime"].apply(format_laptime)
                        display_fastest = display_fastest.drop("LapTime", axis=1)
                        display_fastest = display_fastest.rename(columns={"LapTime_Formatted": "LapTime"})

                        # Reorder columns
                        final_cols = ["Driver", "LapTime"]
                        if "Compound" in display_fastest.columns:
                            final_cols.append("Compound")
                        display_fastest = display_fastest[final_cols]

                        st.dataframe(display_fastest)
                    else:
                        st.info("No valid lap times available.")
                else:
                    st.info("No lap time data available.")


        else:
            if event_info is not None:
                event_date = event_info.get('EventDate', 'Unknown')
                event_name = event_info.get('EventName', 'Unknown Event')
                st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                st.error("Could not load race session. The race may not have started yet.")
            else:
                st.error("Could not load race session. Try another round or year.")

    with tab2:
        st.subheader("Qualifying Session")
        if qualifying_session:
            # Cached session loading for live updates (2 minute cache)
            @st.cache_data(ttl=120, show_spinner=False)
            def load_qualifying_laps(year, rnd):
                try:
                    quali_session = fastf1.get_session(year, rnd, 'Q')
                    quali_session.load(laps=True, telemetry=False, weather=False, messages=False)
                    return quali_session.laps
                except:
                    return pd.DataFrame()

            with st.spinner("Loading qualifying data..."):
                quali_laps = load_qualifying_laps(year, round_number)

            if quali_laps.empty:
                if event_info is not None:
                    event_date = event_info.get('EventDate', 'Unknown')
                    event_name = event_info.get('EventName', 'Unknown Event')
                    st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                    st.warning("No qualifying lap data available yet.")
                else:
                    st.warning("No qualifying lap data available yet.")
            else:
                # Check if we have session identifier to separate Q1, Q2, Q3
                if 'Session' in quali_laps.columns or 'SessionType' in quali_laps.columns:
                    # Create sub-tabs for Q1, Q2, Q3
                    q_tab1, q_tab2, q_tab3 = st.tabs(["Q1", "Q2", "Q3"])

                    session_col = 'Session' if 'Session' in quali_laps.columns else 'SessionType'

                    for i, (tab, session_name) in enumerate([(q_tab1, 'Q1'), (q_tab2, 'Q2'), (q_tab3, 'Q3')], 1):
                        with tab:
                            # Filter laps for this qualifying session
                            session_laps = quali_laps[quali_laps[session_col] == session_name]

                            if session_laps.empty:
                                st.info(f"No {session_name} lap data available.")
                            else:
                                st.subheader(f"{session_name} Lap Times")

                                # Create a copy of the dataframe with formatted lap times and sector times
                                base_cols = ["Driver", "LapTime", "Compound", "TyreLife"]

                                # Add sector times if available
                                sector_cols = []
                                if 'Sector1Time' in session_laps.columns:
                                    sector_cols.append('Sector1Time')
                                if 'Sector2Time' in session_laps.columns:
                                    sector_cols.append('Sector2Time')
                                if 'Sector3Time' in session_laps.columns:
                                    sector_cols.append('Sector3Time')

                                # Only include columns that exist
                                available_cols = [col for col in base_cols if col in session_laps.columns] + sector_cols
                                display_session_laps = session_laps[available_cols].copy()

                                # Clean up driver names
                                if 'BroadcastName' in session_laps.columns:
                                    display_session_laps['Driver'] = session_laps['BroadcastName']
                                elif 'LastName' in session_laps.columns:
                                    display_session_laps['Driver'] = session_laps['LastName']

                                # Format lap time
                                display_session_laps["LapTime_Formatted"] = display_session_laps["LapTime"].apply(format_laptime)

                                # Format sector times if available
                                for sector_col in sector_cols:
                                    if sector_col in display_session_laps.columns:
                                        display_session_laps[f"{sector_col}_Formatted"] = display_session_laps[sector_col].apply(format_laptime)

                                # Sort by actual lap time
                                display_session_laps = display_session_laps.sort_values(by="LapTime")

                                # Replace original columns with formatted ones
                                display_session_laps = display_session_laps.drop("LapTime", axis=1)
                                display_session_laps = display_session_laps.rename(columns={"LapTime_Formatted": "LapTime"})

                                for sector_col in sector_cols:
                                    if f"{sector_col}_Formatted" in display_session_laps.columns:
                                        display_session_laps = display_session_laps.drop(sector_col, axis=1)
                                        display_session_laps = display_session_laps.rename(columns={f"{sector_col}_Formatted": sector_col})

                                # Reorder columns
                                final_cols = ["Driver", "LapTime"]
                                final_cols.extend([col for col in sector_cols if col in display_session_laps.columns])
                                final_cols.extend([col for col in ["Compound", "TyreLife"] if col in display_session_laps.columns])
                                display_session_laps = display_session_laps[final_cols]
                                st.dataframe(display_session_laps)

                                # Show fastest lap for this session
                                st.subheader(f"Fastest {session_name} Lap Per Driver")
                                if not session_laps.empty and 'LapTime' in session_laps.columns:
                                    valid_session_laps = session_laps.dropna(subset=['LapTime'])
                                    valid_session_laps = valid_session_laps[valid_session_laps['LapTime'].notna()]

                                    if not valid_session_laps.empty:
                                        fastest_session_per_driver = valid_session_laps.loc[valid_session_laps.groupby('Driver')['LapTime'].idxmin()]

                                        available_cols = ["Driver", "LapTime"]
                                        if "Compound" in fastest_session_per_driver.columns:
                                            available_cols.append("Compound")

                                        display_fastest_session = fastest_session_per_driver[available_cols].copy()

                                        if 'BroadcastName' in fastest_session_per_driver.columns:
                                            display_fastest_session['Driver'] = fastest_session_per_driver['BroadcastName']
                                        elif 'LastName' in fastest_session_per_driver.columns:
                                            display_fastest_session['Driver'] = fastest_session_per_driver['LastName']

                                        display_fastest_session = display_fastest_session.sort_values(by="LapTime")
                                        display_fastest_session["LapTime_Formatted"] = display_fastest_session["LapTime"].apply(format_laptime)
                                        display_fastest_session = display_fastest_session.drop("LapTime", axis=1)
                                        display_fastest_session = display_fastest_session.rename(columns={"LapTime_Formatted": "LapTime"})

                                        final_cols = ["Driver", "LapTime"]
                                        if "Compound" in display_fastest_session.columns:
                                            final_cols.append("Compound")
                                        display_fastest_session = display_fastest_session[final_cols]

                                        st.dataframe(display_fastest_session)
                                    else:
                                        st.info(f"No valid {session_name} lap times available.")
                                else:
                                    st.info(f"No {session_name} lap time data available.")
                else:
                    # Fallback to original format if no session separation is available
                    st.subheader("All Qualifying Lap Times")
                    display_quali_laps = quali_laps[["Driver", "LapTime", "Compound", "TyreLife"]].copy()

                    if 'BroadcastName' in quali_laps.columns:
                        display_quali_laps['Driver'] = quali_laps['BroadcastName']
                    elif 'LastName' in quali_laps.columns:
                        display_quali_laps['Driver'] = quali_laps['LastName']

                    display_quali_laps["LapTime_Formatted"] = display_quali_laps["LapTime"].apply(format_laptime)
                    display_quali_laps = display_quali_laps.sort_values(by="LapTime")
                    display_quali_laps = display_quali_laps.drop("LapTime", axis=1)
                    display_quali_laps = display_quali_laps.rename(columns={"LapTime_Formatted": "LapTime"})
                    display_quali_laps = display_quali_laps[["Driver", "LapTime", "Compound", "TyreLife"]]
                    st.dataframe(display_quali_laps)

                # Overall fastest qualifying lap (across all sessions)
                st.subheader("Overall Fastest Qualifying Lap Per Driver")
                # Find fastest qualifying lap per driver manually from all lap times
                if not quali_laps.empty and 'LapTime' in quali_laps.columns:
                    # Filter out invalid lap times (NaT, null, or extremely slow times)
                    valid_quali_laps = quali_laps.dropna(subset=['LapTime'])
                    valid_quali_laps = valid_quali_laps[valid_quali_laps['LapTime'].notna()]

                    if not valid_quali_laps.empty:
                        # Group by driver and find the fastest lap for each (across all Q sessions)
                        fastest_quali_per_driver = valid_quali_laps.loc[valid_quali_laps.groupby('Driver')['LapTime'].idxmin()]

                        # Select columns for display
                        available_cols = ["Driver", "LapTime"]
                        if "Compound" in fastest_quali_per_driver.columns:
                            available_cols.append("Compound")
                        # Add session info if available
                        session_col = None
                        if 'Session' in fastest_quali_per_driver.columns:
                            available_cols.append("Session")
                            session_col = 'Session'
                        elif 'SessionType' in fastest_quali_per_driver.columns:
                            available_cols.append("SessionType")
                            session_col = 'SessionType'

                        display_fastest_quali = fastest_quali_per_driver[available_cols].copy()

                        # Clean up driver names
                        if 'BroadcastName' in fastest_quali_per_driver.columns:
                            display_fastest_quali['Driver'] = fastest_quali_per_driver['BroadcastName']
                        elif 'LastName' in fastest_quali_per_driver.columns:
                            display_fastest_quali['Driver'] = fastest_quali_per_driver['LastName']

                        # Sort by lap time (fastest first)
                        display_fastest_quali = display_fastest_quali.sort_values(by="LapTime")

                        # Format the lap times
                        display_fastest_quali["LapTime_Formatted"] = display_fastest_quali["LapTime"].apply(format_laptime)
                        display_fastest_quali = display_fastest_quali.drop("LapTime", axis=1)
                        display_fastest_quali = display_fastest_quali.rename(columns={"LapTime_Formatted": "LapTime"})

                        # Reorder columns
                        final_cols = ["Driver", "LapTime"]
                        if "Compound" in display_fastest_quali.columns:
                            final_cols.append("Compound")
                        if session_col and session_col in display_fastest_quali.columns:
                            final_cols.append(session_col)
                        display_fastest_quali = display_fastest_quali[final_cols]

                        st.dataframe(display_fastest_quali)
                    else:
                        st.info("No valid qualifying lap times available.")
                else:
                    st.info("No qualifying lap time data available.")


        else:
            if event_info is not None:
                event_date = event_info.get('EventDate', 'Unknown')
                event_name = event_info.get('EventName', 'Unknown Event')
                st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                st.error("Could not load qualifying session. Qualifying may not have started yet.")
            else:
                st.error("Could not load qualifying session. Try another round or year.")

    # Sprint Race Tab (only shown for Sprint weekends)
    if is_sprint_weekend:
        with tab3:
            st.subheader("Sprint Race Session")
            if sprint_session:
                # Cached session loading for live updates (2 minute cache)
                @st.cache_data(ttl=120, show_spinner=False)
                def load_sprint_laps(year, rnd):
                    try:
                        sprint_session = fastf1.get_session(year, rnd, 'S')
                        sprint_session.load(laps=True, telemetry=False, weather=False, messages=False)
                        return sprint_session.laps
                    except:
                        return pd.DataFrame()

                with st.spinner("Loading sprint race data..."):
                    sprint_laps = load_sprint_laps(year, round_number)

                if sprint_laps.empty:
                    if event_info is not None:
                        event_date = event_info.get('EventDate', 'Unknown')
                        event_name = event_info.get('EventName', 'Unknown Event')
                        st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                        st.warning("No sprint race lap data available yet.")
                    else:
                        st.warning("No sprint race lap data available yet.")
                else:
                    st.subheader("All Sprint Race Lap Times")
                    # Create a copy of the dataframe with formatted lap times
                    display_sprint_laps = sprint_laps[["Driver", "LapTime", "Compound", "TyreLife"]].copy()
                    display_sprint_laps["LapTime_Formatted"] = display_sprint_laps["LapTime"].apply(format_laptime)

                    # Sort by actual lap time (race order)
                    display_sprint_laps = display_sprint_laps.sort_values(by="LapTime")

                    display_sprint_laps = display_sprint_laps.drop("LapTime", axis=1)
                    display_sprint_laps = display_sprint_laps.rename(columns={"LapTime_Formatted": "LapTime"})
                    # Reorder columns to put LapTime in the right position
                    display_sprint_laps = display_sprint_laps[["Driver", "LapTime", "Compound", "TyreLife"]]
                    st.dataframe(display_sprint_laps)

                    st.subheader("Fastest Sprint Race Lap Per Driver")
                    # Find fastest sprint race lap per driver manually from all lap times
                    if not sprint_laps.empty and 'LapTime' in sprint_laps.columns:
                        # Filter out invalid lap times (NaT, null, or extremely slow times)
                        valid_sprint_laps = sprint_laps.dropna(subset=['LapTime'])
                        valid_sprint_laps = valid_sprint_laps[valid_sprint_laps['LapTime'].notna()]

                        if not valid_sprint_laps.empty:
                            # Group by driver and find the fastest lap for each
                            fastest_sprint_per_driver = valid_sprint_laps.loc[valid_sprint_laps.groupby('Driver')['LapTime'].idxmin()]

                            # Select columns for display
                            available_cols = ["Driver", "LapTime"]
                            if "Compound" in fastest_sprint_per_driver.columns:
                                available_cols.append("Compound")

                            display_fastest_sprint = fastest_sprint_per_driver[available_cols].copy()

                            # Clean up driver names
                            if 'BroadcastName' in fastest_sprint_per_driver.columns:
                                display_fastest_sprint['Driver'] = fastest_sprint_per_driver['BroadcastName']
                            elif 'LastName' in fastest_sprint_per_driver.columns:
                                display_fastest_sprint['Driver'] = fastest_sprint_per_driver['LastName']

                            # Sort by lap time (fastest first)
                            display_fastest_sprint = display_fastest_sprint.sort_values(by="LapTime")

                            # Format the lap times
                            display_fastest_sprint["LapTime_Formatted"] = display_fastest_sprint["LapTime"].apply(format_laptime)
                            display_fastest_sprint = display_fastest_sprint.drop("LapTime", axis=1)
                            display_fastest_sprint = display_fastest_sprint.rename(columns={"LapTime_Formatted": "LapTime"})

                            # Reorder columns
                            final_cols = ["Driver", "LapTime"]
                            if "Compound" in display_fastest_sprint.columns:
                                final_cols.append("Compound")
                            display_fastest_sprint = display_fastest_sprint[final_cols]

                            st.dataframe(display_fastest_sprint)
                        else:
                            st.info("No valid sprint race lap times available.")
                    else:
                        st.info("No sprint race lap time data available.")


            else:
                if event_info is not None:
                    event_date = event_info.get('EventDate', 'Unknown')
                    event_name = event_info.get('EventName', 'Unknown Event')
                    st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                    st.error("Could not load sprint race session. The sprint race may not have started yet.")
                else:
                    st.error("Could not load sprint race session. Try another round or year.")

        # Sprint Qualifying Tab
        with tab4:
            st.subheader("Sprint Qualifying Session")
            if sprint_qualifying_session:
                # Cached session loading for live updates (2 minute cache)
                @st.cache_data(ttl=120, show_spinner=False)
                def load_sprint_qualifying_laps(year, rnd):
                    try:
                        sprint_quali_session = fastf1.get_session(year, rnd, 'SQ')
                        sprint_quali_session.load(laps=True, telemetry=False, weather=False, messages=False)
                        return sprint_quali_session.laps
                    except:
                        return pd.DataFrame()

                with st.spinner("Loading sprint qualifying data..."):
                    sprint_quali_laps = load_sprint_qualifying_laps(year, round_number)

                if sprint_quali_laps.empty:
                    if event_info is not None:
                        event_date = event_info.get('EventDate', 'Unknown')
                        event_name = event_info.get('EventName', 'Unknown Event')
                        st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                        st.warning("No sprint qualifying lap data available yet.")
                    else:
                        st.warning("No sprint qualifying lap data available yet.")
                else:
                    st.subheader("All Sprint Qualifying Lap Times")
                    # Create a copy of the dataframe with formatted lap times
                    display_sprint_quali_laps = sprint_quali_laps[["Driver", "LapTime", "Compound", "TyreLife"]].copy()
                    display_sprint_quali_laps["LapTime_Formatted"] = display_sprint_quali_laps["LapTime"].apply(format_laptime)

                    # Sort by actual lap time
                    display_sprint_quali_laps = display_sprint_quali_laps.sort_values(by="LapTime")

                    display_sprint_quali_laps = display_sprint_quali_laps.drop("LapTime", axis=1)
                    display_sprint_quali_laps = display_sprint_quali_laps.rename(columns={"LapTime_Formatted": "LapTime"})
                    # Reorder columns to put LapTime in the right position
                    display_sprint_quali_laps = display_sprint_quali_laps[["Driver", "LapTime", "Compound", "TyreLife"]]
                    st.dataframe(display_sprint_quali_laps)

                    st.subheader("Fastest Sprint Qualifying Lap Per Driver")
                    # Find fastest sprint qualifying lap per driver manually from all lap times
                    if not sprint_quali_laps.empty and 'LapTime' in sprint_quali_laps.columns:
                        # Filter out invalid lap times (NaT, null, or extremely slow times)
                        valid_sprint_quali_laps = sprint_quali_laps.dropna(subset=['LapTime'])
                        valid_sprint_quali_laps = valid_sprint_quali_laps[valid_sprint_quali_laps['LapTime'].notna()]

                        if not valid_sprint_quali_laps.empty:
                            # Group by driver and find the fastest lap for each
                            fastest_sprint_quali_per_driver = valid_sprint_quali_laps.loc[valid_sprint_quali_laps.groupby('Driver')['LapTime'].idxmin()]

                            # Select columns for display
                            available_cols = ["Driver", "LapTime"]
                            if "Compound" in fastest_sprint_quali_per_driver.columns:
                                available_cols.append("Compound")

                            display_fastest_sprint_quali = fastest_sprint_quali_per_driver[available_cols].copy()

                            # Clean up driver names
                            if 'BroadcastName' in fastest_sprint_quali_per_driver.columns:
                                display_fastest_sprint_quali['Driver'] = fastest_sprint_quali_per_driver['BroadcastName']
                            elif 'LastName' in fastest_sprint_quali_per_driver.columns:
                                display_fastest_sprint_quali['Driver'] = fastest_sprint_quali_per_driver['LastName']

                            # Sort by lap time (fastest first)
                            display_fastest_sprint_quali = display_fastest_sprint_quali.sort_values(by="LapTime")

                            # Format the lap times
                            display_fastest_sprint_quali["LapTime_Formatted"] = display_fastest_sprint_quali["LapTime"].apply(format_laptime)
                            display_fastest_sprint_quali = display_fastest_sprint_quali.drop("LapTime", axis=1)
                            display_fastest_sprint_quali = display_fastest_sprint_quali.rename(columns={"LapTime_Formatted": "LapTime"})

                            # Reorder columns
                            final_cols = ["Driver", "LapTime"]
                            if "Compound" in display_fastest_sprint_quali.columns:
                                final_cols.append("Compound")
                            display_fastest_sprint_quali = display_fastest_sprint_quali[final_cols]

                            st.dataframe(display_fastest_sprint_quali)
                        else:
                            st.info("No valid sprint qualifying lap times available.")
                    else:
                        st.info("No sprint qualifying lap time data available.")


            else:
                if event_info is not None:
                    event_date = event_info.get('EventDate', 'Unknown')
                    event_name = event_info.get('EventName', 'Unknown Event')
                    st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                    st.error("Could not load sprint qualifying session. Sprint qualifying may not have started yet.")
                else:
                    st.error("Could not load sprint qualifying session. Try another round or year.")


# -------- PAGE: RACE RESULTS --------
elif page == "Race Results":
    st.title("Race Results")

    if session:
        try:
            # Cached race results loading for live updates (2 minute cache)
            @st.cache_data(ttl=120, show_spinner=False)
            def load_race_results(year, rnd):
                try:
                    race_session = fastf1.get_session(year, rnd, 'R')
                    race_session.load(laps=False, telemetry=False, weather=False, messages=False)
                    return race_session.results
                except:
                    return pd.DataFrame()

            with st.spinner("Loading race results..."):
                results = load_race_results(year, round_number)
            if results.empty:
                if event_info is not None:
                    event_date = event_info.get('EventDate', 'Unknown')
                    event_name = event_info.get('EventName', 'Unknown Event')
                    st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                    st.warning("Race results not available yet.")
                else:
                    st.warning("Race results not available yet.")
            else:
                st.subheader(f"Final Race Results - Round {round_number}")

                # Format the results for display
                display_results = results[["Position", "DriverNumber", "BroadcastName", "TeamName", "Time", "Status", "Points"]].copy()

                # Format the Time column to show proper race time
                def format_race_time(time_obj):
                    if pd.isna(time_obj):
                        return "N/A"
                    if hasattr(time_obj, 'total_seconds'):
                        total_seconds = time_obj.total_seconds()
                        hours = int(total_seconds // 3600)
                        minutes = int((total_seconds % 3600) // 60)
                        seconds = total_seconds % 60
                        if hours > 0:
                            return f"{hours}:{minutes:02d}:{seconds:06.3f}"
                        else:
                            return f"{minutes}:{seconds:06.3f}"
                    return str(time_obj)

                display_results["Time_Formatted"] = display_results["Time"].apply(format_race_time)
                display_results = display_results.drop("Time", axis=1)
                display_results = display_results.rename(columns={"Time_Formatted": "Time"})

                # Reorder columns
                display_results = display_results[["Position", "DriverNumber", "BroadcastName", "TeamName", "Time", "Status", "Points"]]

                st.dataframe(display_results, use_container_width=True, hide_index=True)

                # Show some race statistics
                col1, col2, col3 = st.columns(3)
                with col1:
                    finishers = len(results[results['Status'] == 'Finished'])
                    st.metric("Finishers", f"{finishers}/{len(results)}")
                with col2:
                    if not results.empty:
                        winner = results.iloc[0]['BroadcastName']
                        st.metric("Winner", winner)
                with col3:
                    dnfs = len(results[results['Status'] != 'Finished'])
                    st.metric("DNFs", dnfs)

        except Exception as e:
            st.error(f"Could not load race results: {e}")
    else:
        if event_info is not None:
            event_date = event_info.get('EventDate', 'Unknown')
            event_name = event_info.get('EventName', 'Unknown Event')
            st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
            st.error("Could not load race session. The race may not have started yet.")
        else:
            st.error("Could not load race session. Try another round or year.")


# -------- PAGE: DRIVER STANDINGS --------
elif page == "Driver Standings":
    st.title(f"Driver Championship Standings - {year}")

    try:
        # Get driver standings up to the current round (ultra-fast)
        @st.cache_data(ttl=3600, show_spinner=False)  # Cache for 1 hour, no spinner
        def get_driver_standings(year, up_to_round):
            try:
                # Quick timeout for faster failure
                import requests
                from requests.adapters import HTTPAdapter
                from urllib3.util.retry import Retry

                # Create a session with short timeout
                session = requests.Session()
                retry_strategy = Retry(total=1, backoff_factor=0.1)
                adapter = HTTPAdapter(max_retries=retry_strategy)
                session.mount("http://", adapter)
                session.mount("https://", adapter)

                # Try direct Ergast API call with timeout
                url = f"http://ergast.com/api/f1/{year}/{up_to_round}/driverStandings.json"
                response = session.get(url, timeout=5)  # 5 second timeout

                if response.status_code == 200:
                    data = response.json()
                    standings_list = data['MRData']['StandingsTable']['StandingsLists']

                    if standings_list:
                        driver_standings = standings_list[0]['DriverStandings']

                        # Convert to DataFrame
                        standings_data = []
                        for standing in driver_standings:
                            driver = standing['Driver']
                            constructor = standing['Constructors'][0] if standing['Constructors'] else {}

                            standings_data.append({
                                'Position': int(standing['position']),
                                'BroadcastName': driver.get('familyName', '').upper(),
                                'TeamName': constructor.get('name', ''),
                                'Points': float(standing['points'])
                            })

                        return pd.DataFrame(standings_data)

                # If direct API fails, return empty DataFrame quickly
                return pd.DataFrame()

            except Exception as e:
                # Fast fallback - return empty DataFrame immediately
                return pd.DataFrame()

        standings = get_driver_standings(year, round_number)

        if standings.empty:
            st.warning("No driver standings data available yet.")
        else:
            st.subheader(f"Championship Standings after Round {round_number}")
            st.dataframe(standings, use_container_width=True, hide_index=True)

            # Show championship leader info
            if len(standings) > 0:
                leader = standings.iloc[0]
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Championship Leader", leader['BroadcastName'])
                with col2:
                    st.metric("Points", int(leader['Points']))
                with col3:
                    if len(standings) > 1:
                        gap = leader['Points'] - standings.iloc[1]['Points']
                        st.metric("Lead", f"{int(gap)} pts")
                    else:
                        st.metric("Lead", "N/A")

    except Exception as e:
        st.error(f"Could not load driver standings: {e}")


# -------- PAGE: CONSTRUCTOR STANDINGS --------
elif page == "Constructor Standings":
    st.title(f"Constructor Championship Standings - {year}")

    try:
        # Get constructor standings up to the current round (ultra-fast)
        @st.cache_data(ttl=3600, show_spinner=False)  # Cache for 1 hour, no spinner
        def get_constructor_standings(year, up_to_round):
            try:
                # Quick timeout for faster failure
                import requests
                from requests.adapters import HTTPAdapter
                from urllib3.util.retry import Retry

                # Create a session with short timeout
                session = requests.Session()
                retry_strategy = Retry(total=1, backoff_factor=0.1)
                adapter = HTTPAdapter(max_retries=retry_strategy)
                session.mount("http://", adapter)
                session.mount("https://", adapter)

                # Try direct Ergast API call with timeout
                url = f"http://ergast.com/api/f1/{year}/{up_to_round}/constructorStandings.json"
                response = session.get(url, timeout=5)  # 5 second timeout

                if response.status_code == 200:
                    data = response.json()
                    standings_list = data['MRData']['StandingsTable']['StandingsLists']

                    if standings_list:
                        constructor_standings = standings_list[0]['ConstructorStandings']

                        # Convert to DataFrame
                        standings_data = []
                        for standing in constructor_standings:
                            standings_data.append({
                                'Position': int(standing['position']),
                                'TeamName': standing['Constructor']['name'],
                                'Points': float(standing['points'])
                            })

                        return pd.DataFrame(standings_data)

                # If direct API fails, return empty DataFrame quickly
                return pd.DataFrame()

            except Exception as e:
                # Fast fallback - return empty DataFrame immediately
                return pd.DataFrame()

        constructor_standings = get_constructor_standings(year, round_number)

        if constructor_standings.empty:
            st.warning("No constructor standings data available yet.")
        else:
            st.subheader(f"Constructor Championship after Round {round_number}")
            st.dataframe(constructor_standings, use_container_width=True, hide_index=True)

            # Show constructor championship leader info
            if len(constructor_standings) > 0:
                leader = constructor_standings.iloc[0]
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Leading Constructor", leader['TeamName'])
                with col2:
                    st.metric("Points", int(leader['Points']))
                with col3:
                    if len(constructor_standings) > 1:
                        gap = leader['Points'] - constructor_standings.iloc[1]['Points']
                        st.metric("Lead", f"{int(gap)} pts")
                    else:
                        st.metric("Lead", "N/A")

    except Exception as e:
        st.error(f"Could not load constructor standings: {e}")


# -------- PAGE: EVENT SCHEDULE --------
elif page == "Event Schedule":
    st.title(f"F1 {year} Event Schedule")
    try:
        sched = fastf1.get_event_schedule(year)
        if sched.empty:
            st.warning("No schedule found for the selected year.")
        else:
            # Display the full schedule with better formatting
            st.subheader(f"All {len(sched)} races in {year}")

            # Select relevant columns for display
            display_columns = ['RoundNumber', 'EventName', 'Location', 'Country', 'EventDate', 'EventFormat']
            available_columns = [col for col in display_columns if col in sched.columns]

            # Format the dataframe for better readability
            schedule_df = sched[available_columns].copy()

            # Sort by round number
            schedule_df = schedule_df.sort_values('RoundNumber')

            # Display the schedule
            st.dataframe(
                schedule_df,
                use_container_width=True,
                hide_index=True
            )

            # Show some statistics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Races", len(sched))
            with col2:
                if 'EventDate' in sched.columns:
                    next_race = sched[sched['EventDate'] > datetime.now().date()]
                    if not next_race.empty:
                        st.metric("Next Race", next_race.iloc[0]['EventName'])
                    else:
                        st.metric("Next Race", "Season Complete")
            with col3:
                unique_countries = sched['Country'].nunique() if 'Country' in sched.columns else 0
                st.metric("Countries", unique_countries)

    except Exception as e:
        st.error(f"Could not load schedule: {e}")


# -------- PAGE: RACE CONTROL --------
elif page == "Race Control":
    st.title("🏁 Race Control & Track Status")

    # Show last updated time for live data
    from datetime import datetime
    current_time = datetime.now().strftime("%H:%M:%S")
    st.caption(f"🕒 Last updated: {current_time} | Auto-refresh every 10 seconds")

    if session:
        # Load session data for race control with persistent caching
        @st.cache_data(ttl=86400, show_spinner=False)  # 24 hour cache to persist after race
        def load_race_control_data(year, rnd):
            try:
                race_session = fastf1.get_session(year, rnd, 'R')
                race_session.load(laps=False, telemetry=False, weather=False, messages=True)

                # Also try to load results for penalty cross-reference
                try:
                    race_session.load(laps=True, telemetry=False, weather=False, messages=True)
                    results = getattr(race_session, 'results', pd.DataFrame())
                    laps = getattr(race_session, 'laps', pd.DataFrame())
                except:
                    results = pd.DataFrame()
                    laps = pd.DataFrame()

                return {
                    'track_status': getattr(race_session, 'track_status', pd.DataFrame()),
                    'race_control_messages': getattr(race_session, 'race_control_messages', pd.DataFrame()),
                    'results': results,
                    'laps': laps
                }
            except:
                return {
                    'track_status': pd.DataFrame(),
                    'race_control_messages': pd.DataFrame(),
                    'results': pd.DataFrame(),
                    'laps': pd.DataFrame()
                }

        with st.spinner("Loading race control data..."):
            race_control_data = load_race_control_data(year, round_number)
            track_status = race_control_data['track_status']
            race_control_messages = race_control_data['race_control_messages']
            results = race_control_data['results']
            laps = race_control_data['laps']

        # Track Status Codes Reference
        st.subheader("📊 Track Status Codes Reference")
        status_info = {
            "1": {"status": "Track Clear", "flag": "🟢 Green Flag", "description": "Normal racing conditions"},
            "2": {"status": "Yellow Flag", "flag": "🟡 Yellow Flag", "description": "Caution - No overtaking"},
            "3": {"status": "Safety Car", "flag": "🚗 Safety Car", "description": "Safety car deployed on track"},
            "4": {"status": "Red Flag", "flag": "🔴 Red Flag", "description": "Session stopped"},
            "5": {"status": "Virtual Safety Car", "flag": "🟡 VSC", "description": "Virtual Safety Car active"},
            "6": {"status": "VSC Ending", "flag": "🟡 VSC Ending", "description": "Virtual Safety Car ending"},
            "7": {"status": "Safety Car Ending", "flag": "🚗 SC Ending", "description": "Safety car returning to pits"}
        }

        # Display status codes in a nice format
        cols = st.columns(4)
        for i, (code, info) in enumerate(status_info.items()):
            with cols[i % 4]:
                st.info(f"**{code}** - {info['flag']}\n\n{info['description']}")

        # Current Track Status
        st.subheader("🚦 Current Track Status")
        if not track_status.empty:
            # Get the most recent status
            latest_status = track_status.iloc[-1] if len(track_status) > 0 else None

            if latest_status is not None and 'Status' in track_status.columns:
                status_code = str(latest_status['Status'])
                if status_code in status_info:
                    status_details = status_info[status_code]
                    st.success(f"**Current Status**: {status_details['flag']} - {status_details['status']}")
                    st.write(f"*{status_details['description']}*")
                else:
                    st.warning(f"**Current Status**: Code {status_code} (Unknown)")

            # Show track status history
            st.subheader("📈 Track Status History")
            if 'Status' in track_status.columns:
                display_status = track_status.copy()

                # Add human-readable descriptions
                display_status['Status_Description'] = display_status['Status'].astype(str).map(
                    {code: f"{info['flag']} - {info['status']}" for code, info in status_info.items()}
                ).fillna('Unknown Status')

                # Format time columns if available
                time_columns = ['Time', 'SessionTime', 'Date']
                for col in time_columns:
                    if col in display_status.columns:
                        try:
                            display_status[col] = pd.to_datetime(display_status[col]).dt.strftime('%H:%M:%S')
                        except:
                            pass

                # Select relevant columns for display
                display_columns = ['Status', 'Status_Description']
                for col in time_columns:
                    if col in display_status.columns:
                        display_columns.insert(-1, col)

                available_columns = [col for col in display_columns if col in display_status.columns]
                st.dataframe(display_status[available_columns], use_container_width=True, hide_index=True)
            else:
                st.dataframe(track_status, use_container_width=True, hide_index=True)
        else:
            st.info("No track status data available.")

        # Detailed Penalties Section
        st.subheader("🚨 Race Penalties & Sanctions")

        # Extract and analyze penalties
        penalties_data = []
        if not race_control_messages.empty and 'Message' in race_control_messages.columns:
            for idx, row in race_control_messages.iterrows():
                message = str(row['Message']).lower()

                # Check if this is a penalty message
                if any(word in message for word in ['penalty', 'penalised', 'penalized', 'time penalty', 'grid penalty', 'reprimand']):
                    penalty_info = {
                        'Message': row['Message'],
                        'Driver': 'Unknown',
                        'Car_Number': 'Unknown',
                        'Penalty_Type': 'Unknown',
                        'Penalty_Details': row['Message'],
                        'Lap': 'Unknown'
                    }

                    # Extract driver information
                    if 'Driver' in row and pd.notna(row['Driver']):
                        penalty_info['Driver'] = row['Driver']
                    elif 'CarNumber' in row and pd.notna(row['CarNumber']):
                        penalty_info['Car_Number'] = str(row['CarNumber'])
                        # Try to match car number to driver from results
                        if not results.empty and 'DriverNumber' in results.columns:
                            driver_match = results[results['DriverNumber'] == row['CarNumber']]
                            if not driver_match.empty and 'BroadcastName' in driver_match.columns:
                                penalty_info['Driver'] = driver_match.iloc[0]['BroadcastName']

                    # Extract car number from message if not found
                    import re
                    if penalty_info['Car_Number'] == 'Unknown':
                        car_match = re.search(r'car (\d+)|#(\d+)|no\.?\s*(\d+)', message)
                        if car_match:
                            car_num = car_match.group(1) or car_match.group(2) or car_match.group(3)
                            penalty_info['Car_Number'] = car_num
                            # Try to match to driver
                            if not results.empty and 'DriverNumber' in results.columns:
                                driver_match = results[results['DriverNumber'].astype(str) == car_num]
                                if not driver_match.empty and 'BroadcastName' in driver_match.columns:
                                    penalty_info['Driver'] = driver_match.iloc[0]['BroadcastName']

                    # Extract driver name from message if not found
                    if penalty_info['Driver'] == 'Unknown':
                        # Common driver name patterns
                        driver_patterns = [
                            r'([A-Z][a-z]+)\s+([A-Z][a-z]+)',  # First Last
                            r'([A-Z]{3})',  # Three letter code
                        ]
                        for pattern in driver_patterns:
                            driver_match = re.search(pattern, row['Message'])
                            if driver_match:
                                penalty_info['Driver'] = driver_match.group(0)
                                break

                    # Determine penalty type
                    if 'time penalty' in message:
                        if '5 sec' in message or '5-sec' in message:
                            penalty_info['Penalty_Type'] = '5 Second Time Penalty'
                        elif '10 sec' in message or '10-sec' in message:
                            penalty_info['Penalty_Type'] = '10 Second Time Penalty'
                        elif '30 sec' in message or '30-sec' in message:
                            penalty_info['Penalty_Type'] = '30 Second Time Penalty'
                        else:
                            penalty_info['Penalty_Type'] = 'Time Penalty'
                    elif 'grid penalty' in message:
                        penalty_info['Penalty_Type'] = 'Grid Penalty'
                    elif 'stop and go' in message or 'stop-and-go' in message:
                        penalty_info['Penalty_Type'] = 'Stop and Go Penalty'
                    elif 'drive through' in message or 'drive-through' in message:
                        penalty_info['Penalty_Type'] = 'Drive Through Penalty'
                    elif 'reprimand' in message:
                        penalty_info['Penalty_Type'] = 'Reprimand'
                    elif 'disqualified' in message or 'dsq' in message:
                        penalty_info['Penalty_Type'] = 'Disqualification'
                    elif 'warning' in message:
                        penalty_info['Penalty_Type'] = 'Warning'

                    # Extract lap information with multiple patterns
                    lap_patterns = [
                        r'lap (\d+)',
                        r'on lap (\d+)',
                        r'at lap (\d+)',
                        r'during lap (\d+)',
                        r'in lap (\d+)',
                        r'lap\s*(\d+)',
                        r'l(\d+)',  # Sometimes written as L15, etc.
                    ]

                    for pattern in lap_patterns:
                        lap_match = re.search(pattern, message)
                        if lap_match:
                            penalty_info['Lap'] = lap_match.group(1)
                            break

                    # If no lap found in message, try to extract from session time or other context
                    if penalty_info['Lap'] == 'Unknown' and not laps.empty:
                        # Try to correlate with lap data if we have session time
                        if 'SessionTime' in row and pd.notna(row['SessionTime']):
                            try:
                                session_time = pd.to_timedelta(row['SessionTime'])
                                # Find the lap that was happening at this session time
                                if 'LapStartTime' in laps.columns:
                                    closest_lap = laps[laps['LapStartTime'] <= session_time].tail(1)
                                    if not closest_lap.empty and 'LapNumber' in closest_lap.columns:
                                        penalty_info['Lap'] = str(closest_lap.iloc[0]['LapNumber'])
                            except:
                                pass

                    penalties_data.append(penalty_info)

        if penalties_data:
            penalties_df = pd.DataFrame(penalties_data)

            # Display penalties in a clean format
            st.write(f"**Total Penalties Issued: {len(penalties_df)}**")

            # Create a summary table focused on lap information
            display_penalties = penalties_df[['Lap', 'Driver', 'Car_Number', 'Penalty_Type', 'Penalty_Details']].copy()
            display_penalties.columns = ['Lap', 'Driver', 'Car #', 'Penalty Type', 'Details']

            # Sort by lap number (convert to numeric for proper sorting)
            display_penalties['Lap_Numeric'] = pd.to_numeric(display_penalties['Lap'], errors='coerce')
            display_penalties = display_penalties.sort_values('Lap_Numeric', na_position='last')
            display_penalties = display_penalties.drop('Lap_Numeric', axis=1)

            st.dataframe(display_penalties, use_container_width=True, hide_index=True)

            # Penalty statistics
            if len(penalties_df) > 0:
                col1, col2, col3 = st.columns(3)

                with col1:
                    penalty_types = penalties_df['Penalty_Type'].value_counts()
                    st.write("**Penalty Types:**")
                    for penalty_type, count in penalty_types.items():
                        st.write(f"• {penalty_type}: {count}")

                with col2:
                    drivers_with_penalties = penalties_df['Driver'].value_counts()
                    st.write("**Drivers with Penalties:**")
                    for driver, count in drivers_with_penalties.head(5).items():
                        if driver != 'Unknown':
                            st.write(f"• {driver}: {count}")

                with col3:
                    laps_with_penalties = penalties_df[penalties_df['Lap'] != 'Unknown']['Lap'].value_counts()
                    if not laps_with_penalties.empty:
                        st.write("**Laps with Penalties:**")
                        for lap, count in laps_with_penalties.head(5).items():
                            st.write(f"• Lap {lap}: {count}")
        else:
            st.success("✅ No penalties issued during this race!")

        # Race Control Messages & Penalties
        st.subheader("📢 Race Control Messages & Penalties")
        if not race_control_messages.empty:
            # Filter and categorize messages
            messages_df = race_control_messages.copy()

            # Remove time columns - we focus on lap-based information
            # time_columns = ['Time', 'SessionTime', 'Date']
            # for col in time_columns:
            #     if col in messages_df.columns:
            #         try:
            #             messages_df[col] = pd.to_datetime(messages_df[col]).dt.strftime('%H:%M:%S')
            #         except:
            #             pass

            # Categorize messages
            if 'Message' in messages_df.columns:
                # Create category based on message content
                def categorize_message(message):
                    message_lower = str(message).lower()
                    if any(word in message_lower for word in ['penalty', 'penalised', 'time penalty', 'grid penalty']):
                        return "🚨 Penalty"
                    elif any(word in message_lower for word in ['investigation', 'incident', 'noted']):
                        return "🔍 Investigation"
                    elif any(word in message_lower for word in ['safety car', 'virtual safety car', 'vsc']):
                        return "🚗 Safety Car"
                    elif any(word in message_lower for word in ['flag', 'yellow', 'red', 'green']):
                        return "🏁 Flag"
                    elif any(word in message_lower for word in ['drs', 'enabled', 'disabled']):
                        return "⚡ DRS"
                    else:
                        return "📢 General"

                messages_df['Category'] = messages_df['Message'].apply(categorize_message)

                # Sort by message order (no time sorting)
                # if 'Time' in messages_df.columns:
                #     try:
                #         messages_df = messages_df.sort_values('Time', ascending=False)
                #     except:
                #         pass

                # Select columns for display (no time columns)
                display_columns = ['Category', 'Message']

                # Add driver/car info if available
                if 'Driver' in messages_df.columns:
                    display_columns.insert(-1, 'Driver')
                if 'CarNumber' in messages_df.columns:
                    display_columns.insert(-1, 'CarNumber')

                available_columns = [col for col in display_columns if col in messages_df.columns]

                # Display the messages
                st.dataframe(messages_df[available_columns], use_container_width=True, hide_index=True)

                # Show summary statistics
                if 'Category' in messages_df.columns:
                    st.subheader("📊 Message Summary")
                    category_counts = messages_df['Category'].value_counts()

                    cols = st.columns(len(category_counts))
                    for i, (category, count) in enumerate(category_counts.items()):
                        with cols[i]:
                            st.metric(category, count)
            else:
                st.dataframe(race_control_messages, use_container_width=True, hide_index=True)
        else:
            st.info("No race control messages available.")
    else:
        if event_info is not None:
            event_date = event_info.get('EventDate', 'Unknown')
            event_name = event_info.get('EventName', 'Unknown Event')
            st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
            st.error("Could not load race session. The race may not have started yet.")
        else:
            st.error("Could not load race session. Try another round or year.")



