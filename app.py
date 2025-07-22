
import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
import os

# --- DATA LOADING ---
@st.cache_resource
def load_data():
    df = pd.read_excel("Texas_Offense_Type_by_Agency_2023.xlsx", header=0)
    df.columns = df.columns.str.strip().str.replace("\n", " ").str.replace(" ", "_")
    return df

@st.cache_resource
def load_places():
    gdf = gpd.read_file("tl_2023_48_place.shp")
    gdf["centroid"] = gdf.geometry.centroid
    return gdf

# --- APP LOGIC ---
st.set_page_config(layout="wide")
st.title("Texas Crime Rate Interactive Heatmap")
st.caption("Search Texas cities and visualize crime by offense type. Data: TX DPS 2023")

df = load_data()
gdf_places = load_places()

# Identify all numeric crime-related columns
exclude_cols = {"Agency_Name", "Agency_Type", "Population"}
crime_types = [col for col in df.columns if col not in exclude_cols and pd.api.types.is_numeric_dtype(df[col])]

if crime_types:
    crime_col = st.sidebar.selectbox("Choose crime category:", sorted(crime_types))
else:
    st.error("No numeric crime category columns found in the dataset.")
    st.stop()

# Search bar
search_city = st.sidebar.text_input("Search for a Texas city:")

# --- PROCESS DATA ---
# Merge data and geometry
def get_city_latlon(name):
    row = gdf_places[gdf_places["NAME"].str.lower() == name.lower()]
    if not row.empty:
        return row.iloc[0]["centroid"].y, row.iloc[0]["centroid"].x
    else:
        return None, None

df["latitude"] = df["Agency_Name"].apply(lambda x: get_city_latlon(str(x).strip())[0] if pd.notnull(x) else None)
df["longitude"] = df["Agency_Name"].apply(lambda x: get_city_latlon(str(x).strip())[1] if pd.notnull(x) else None)

# Ensure numeric and drop rows without lat/lon or crime data
df[crime_col] = pd.to_numeric(df[crime_col], errors="coerce")
df_heat = df.dropna(subset=["latitude", "longitude", crime_col])

# --- MAP ---
st.subheader("Crime Heatmap")

if not df_heat.empty:
    avg_lat = df_heat["latitude"].mean()
    avg_lon = df_heat["longitude"].mean()
else:
    avg_lat, avg_lon = 31.9686, -99.9018

m = folium.Map(location=[avg_lat, avg_lon], zoom_start=6)

heat_data = [
    [row["latitude"], row["longitude"], row[crime_col]]
    for _, row in df_heat.iterrows()
]

if heat_data:
    HeatMap(heat_data, radius=15, blur=10, max_zoom=9).add_to(m)

st_data = st_folium(m, width=900, height=600)

# --- CITY SEARCH + TABLES ---
if search_city:
    results = df[df["Agency_Name"].str.lower().str.contains(search_city.lower(), na=False)]
    if not results.empty:
        city = results.iloc[0]
        st.markdown(f"### {city['Agency_Name']}")
        st.write(f"**{crime_col}**: {city[crime_col]:,.0f}")
        st.write(f"Coordinates: ({city['latitude']:.4f}, {city['longitude']:.4f})")
    else:
        st.warning("City not found. Try a different spelling?")

# Top/Bottom tables
st.subheader(f"Safest & Most Dangerous Cities by {crime_col}")
sorted_df = df_heat[["Agency_Name", crime_col]].sort_values(by=crime_col)
col1, col2 = st.columns(2)
with col1:
    st.markdown("#### Safest (Lowest Crime)")
    st.dataframe(sorted_df.head(10).reset_index(drop=True))
with col2:
    st.markdown("#### Most Dangerous (Highest Crime)")
    st.dataframe(sorted_df.tail(10).sort_values(by=crime_col, ascending=False).reset_index(drop=True))
