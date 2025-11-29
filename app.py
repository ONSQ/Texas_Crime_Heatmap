import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
from folium import CircleMarker, Tooltip
from streamlit_folium import st_folium

import config
import data_manager

# --- APP CONFIG ---
st.set_page_config(layout="wide")
st.title("Texas Crime Rate Interactive Heatmap")
st.caption("Search Texas cities and visualize crime by offense type.")
st.caption("Data from the 2023 FBI NIBRS, TX DP2023, and USCensus Datasets. All crimes listed are preadjudicated and not convictions.")    
st.caption("Webapp by Owen Eskew (WGN372)")

# --- DATA LOADING ---
st.sidebar.header("📂 Data Management")

# Year Selector
available_years = sorted(list(config.DATA_FILES.keys()), reverse=True)
selected_year = st.sidebar.selectbox("Select Year", available_years, index=0)

uploaded_file = st.sidebar.file_uploader("Upload your own Crime CSV", type=["csv"])

if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file)
        df.columns = df.columns.str.strip().str.replace("\n", " ")
        st.sidebar.success("Custom data loaded!")
    except Exception as e:
        st.sidebar.error(f"Error loading file: {e}")
        st.stop()
else:
    df = data_manager.load_data(selected_year)

land_df = data_manager.load_land_area()
gdf_places = data_manager.load_places()

# Merge and Process
# Ensure column names are consistent and exist
if "Agency" not in df.columns:
    st.error(f"Column 'Agency' not found in {config.DATA_FILE}")
    st.stop()

if "city" not in land_df.columns:
    st.error(f"Column 'city' not found in {config.LAND_AREA_FILE}")
    st.stop()

df = data_manager.merge_and_process_data(df, land_df)

# Add coordinates (this might be slow, consider caching if it becomes an issue)
# For now, we do it on the fly as in the original app, but using the helper
# To avoid re-calculating on every rerun, we could cache this step in data_manager
# But since we can't easily cache the mutation, let's keep it here for now.
# Optimization: Only calculate for displayed cities? No, heatmap needs all.
# Let's assume the original performance was acceptable.
df = data_manager.add_coordinates(df, gdf_places)

# --- SIDEBAR ---
# Search bar
search_city = st.sidebar.text_input("Search for a Texas city:")

# Identify all numeric crime-related columns (absolute numbers only)
crime_types = [col for col in df.columns if col not in config.EXCLUDE_COLS 
               and pd.api.types.is_numeric_dtype(df[col]) and "%" not in col]

if crime_types:
    # Sort the list and move "Total Offenses" to the top if it exists
    sorted_crime_types = sorted(crime_types)
    if "Total Offenses" in sorted_crime_types:
        sorted_crime_types.remove("Total Offenses")
        sorted_crime_types.insert(0, "Total Offenses")

    # Dropdown default = first item (Total Offenses)
    crime_col = st.sidebar.selectbox(
        "Choose crime category (absolute numbers):",
        sorted_crime_types,
        index=0
    )
else:
    st.error("No numeric crime category columns found in the dataset.")
    st.stop()

# Toggle for using % vs absolute
use_percentage = st.sidebar.checkbox("Use % (crime per population) for heatmap", value=False)

# --- PREPARE DATA FOR DISPLAY ---
# Ensure numeric
df[crime_col] = pd.to_numeric(df[crime_col], errors="coerce")
df_heat = df.dropna(subset=["latitude", "longitude", crime_col])

# --- TABS LAYOUT ---
tab1, tab2, tab3 = st.tabs(["🗺️ Heatmap & Search", "📊 Data Analysis", "🔮 Prediction Model"])

with tab1:
    # --- METRICS ROW ---
    # Show statewide summary info at the top
    total_population = df["Population"].sum()
    total_crime = df[crime_col].sum()
    
    st.markdown("### 🇨🇱 Texas Statewide Snapshot")
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Total Population", f"{int(total_population):,}")
    col_m2.metric(f"Total {crime_col}", f"{int(total_crime):,}")
    
    if total_population > 0:
        percent_value = (total_crime / total_population) * 100
        col_m3.metric("Crime Rate", f"{percent_value:.2f}%")

    # --- MAP SECTION ---
    st.subheader(f"{crime_col} Heatmap")

    avg_lat, avg_lon = config.DEFAULT_LAT, config.DEFAULT_LON
    zoom_level = config.DEFAULT_ZOOM

    if search_city:
        results = df[df["Agency"].str.lower().str.contains(search_city.lower(), na=False)]
        if not results.empty:
            city = results.iloc[0]
            if pd.notnull(city["latitude"]) and pd.notnull(city["longitude"]):
                avg_lat, avg_lon = city["latitude"], city["longitude"]
                zoom_level = config.CITY_ZOOM
            
            # Display city stats in an expander or just below
            with st.expander(f"Details for {city['Agency']}", expanded=True):
                c1, c2 = st.columns(2)
                with c1:
                    st.write(f"**Coordinates:** ({city['latitude']:.4f}, {city['longitude']:.4f})")
                    st.write(f"**Population:** {int(city['Population']):,}")
                with c2:
                    abs_val = city[crime_col]
                    pct_val = city.get(f"{crime_col} %")
                    if pd.notnull(abs_val):
                        st.write(f"**{crime_col}:** {abs_val:,.0f}")
                    if pd.notnull(pct_val):
                        st.write(f"**Rate:** {pct_val:.2f}%")
        else:
            st.warning("City not found. Try a different spelling?")

    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=zoom_level)

    # Decide heatmap data
    if use_percentage:
        percent_col = f"{crime_col} %"
        if percent_col not in df_heat.columns:
            st.error(f"No percentage data found for {crime_col}.")
            st.stop()

        heat_data = [
            [row["latitude"], row["longitude"], row[percent_col]]
            for _, row in df_heat.iterrows()
            if pd.notnull(row[percent_col]) and row[percent_col] > 0
        ]
    else:
        heat_data = [
            [row["latitude"], row["longitude"], row[crime_col]]
            for _, row in df_heat.iterrows()
            if pd.notnull(row[crime_col]) and row[crime_col] > 0
        ]

    if heat_data:
        HeatMap(
            heat_data,
            radius=15,
            blur=10,
            max_zoom=9,
            gradient={0.0: 'blue', 0.2: 'green', 0.4: 'yellow', 0.6: 'orange', 0.8: 'red', 1.0: 'darkred'}
        ).add_to(m)

    # Add invisible markers with improved tooltips
    for _, row in df_heat.iterrows():
        abs_value = row[crime_col]
        percent_value = row.get(f"{crime_col} %", None)

        # HTML styled tooltip
        tooltip_text = f"""
        <div style="font-family: sans-serif; font-size: 12px;">
            <b>{row['Agency']}</b><br>
            Population: {int(row['Population']):,}<br>
            {crime_col}: {abs_value:,.0f}<br>
        """
        if percent_value is not None and pd.notnull(percent_value):
            tooltip_text += f"Rate: {percent_value:.2f}%"
        tooltip_text += "</div>"

        CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=5,
            color="#00000000",
            fill=True,
            fill_color="#000000",
            fill_opacity=0.01, # Almost invisible
            tooltip=Tooltip(tooltip_text, sticky=True)
        ).add_to(m)

    st_folium(m, width=900, height=600)

with tab2:
    # --- TOP/BOTTOM TABLES ---
    st.subheader(f"Safest & Most Dangerous Cities by {crime_col}")
    
    # Add a filter for population to make this more meaningful
    min_pop = st.slider("Minimum Population Filter", 0, 1000000, 0, 1000)
    
    filtered_df = df_heat[df_heat["Population"] >= min_pop]
    
    percent_col = f"{crime_col} %"
    cols_to_show = ["Agency", "Population", crime_col]
    if percent_col in filtered_df.columns:
        cols_to_show.append(percent_col)

    sorted_df = filtered_df[cols_to_show].sort_values(by=percent_col if percent_col in filtered_df.columns else crime_col)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### ✅ Safest (Lowest Crime)")
        st.dataframe(sorted_df.head(10).reset_index(drop=True), use_container_width=True)
    with col2:
        st.markdown("#### ⚠️ Most Dangerous (Highest Crime)")
        st.dataframe(sorted_df.tail(10).sort_values(by=percent_col if percent_col in filtered_df.columns else crime_col, ascending=False).reset_index(drop=True), use_container_width=True)

    # Download Button
    csv = filtered_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Filtered Data as CSV",
        data=csv,
        file_name='texas_crime_filtered.csv',
        mime='text/csv',
    )

    st.divider()
    
    # --- CORRELATION ANALYSIS ---
    st.subheader("🔗 Correlation Analysis")
    st.caption("How different variables relate to each other (1.0 = perfect positive correlation, -1.0 = perfect negative correlation).")
    
    # Select numeric columns only
    numeric_df = filtered_df.select_dtypes(include=['float64', 'int64'])
    # Drop columns that are not useful for correlation
    cols_to_drop = ["latitude", "longitude"]
    numeric_df = numeric_df.drop(columns=[c for c in cols_to_drop if c in numeric_df.columns], errors='ignore')
    
    if not numeric_df.empty:
        corr_matrix = numeric_df.corr()
        st.dataframe(corr_matrix.style.background_gradient(cmap="coolwarm", axis=None), use_container_width=True)
    else:
        st.info("Not enough numeric data for correlation analysis.")

with tab3:
    # --- PREDICTION ---
    st.subheader("🔮 Future Trend Prediction")
    st.info("This model uses linear regression on the current dataset to estimate crime levels based on population growth.")

    # Determine population value
    if search_city:
        results = df[df["Agency"].str.lower().str.contains(search_city.lower(), na=False)]
        if not results.empty:
            city = results.iloc[0]
            pop_int = int(city["Population"])
            st.markdown(f"### Prediction for **{city['Agency']}**")
        else:
            pop_int = int(df["Population"].sum())
            st.markdown("### Statewide Prediction")
    else:
        pop_int = int(df["Population"].sum())
        st.markdown("### Statewide Prediction")

    lower, upper = data_manager.predict_crime_growth(df, crime_col, pop_int)

    col_p1, col_p2 = st.columns(2)
    
    with col_p1:
        st.write(f"**Current Population:** {pop_int:,}")
        st.write(
            f"**Predicted Population (±5%):** "
            f"{int(pop_int * 0.95):,} - {int(pop_int * 1.05):,}"
        )

    with col_p2:
        if lower is not None and upper is not None:
            lower_percent = (lower / pop_int) * 100
            upper_percent = (upper / pop_int) * 100
            
            st.metric(
                label=f"Estimated {crime_col} Range",
                value=f"{lower:,} - {upper:,}",
                delta=None
            )
            st.caption(f"Implied Rate: {lower_percent:.2f}% - {upper_percent:.2f}%")
        else:
            st.warning("Could not calculate prediction based on current data.")

    # --- VISUALIZATION ---
    st.markdown("#### 📈 Visualizing the Trend")
    
    # Prepare data for scatter plot
    if crime_col in df.columns and "Population" in df.columns:
        chart_data = df.dropna(subset=[crime_col, "Population"])
        
        # Add the prediction point if available
        if lower is not None and upper is not None:
            # We plot the average prediction
            pred_val = (lower + upper) / 2
            # Create a small dataframe for the prediction point
            pred_df = pd.DataFrame({
                "Population": [int(pop_int * 1.05)], # Future pop
                crime_col: [pred_val],
                "Type": ["Prediction"]
            })
            chart_data["Type"] = "Historical"
            combined_data = pd.concat([chart_data, pred_df], ignore_index=True)
            
            st.scatter_chart(
                combined_data,
                x="Population",
                y=crime_col,
                color="Type",
                size=20
            )
        else:
            st.scatter_chart(chart_data, x="Population", y=crime_col)

# --- TREND ANALYSIS (If multiple years exist) ---
if len(config.DATA_FILES) > 1:
    with st.expander("📈 Trend Analysis (Multi-Year)"):
        st.subheader("Time Series Analysis")
        
        all_years_df = data_manager.load_all_years()
        
        if not all_years_df.empty:
            # City selection for trend
            cities = sorted(all_years_df["Agency"].dropna().unique())
            selected_cities_trend = st.multiselect("Select Cities to Compare", cities, default=cities[:3] if len(cities) > 3 else cities)
            
            if selected_cities_trend:
                trend_data = all_years_df[all_years_df["Agency"].isin(selected_cities_trend)]
                
                if crime_col in trend_data.columns:
                    st.line_chart(
                        trend_data,
                        x="Year",
                        y=crime_col,
                        color="Agency"
                    )
                else:
                    st.warning(f"Column '{crime_col}' not found in multi-year data.")
            else:
                st.info("Select cities to see the trend.")
        else:
            st.warning("Could not load multi-year data.")

