import pandas as pd
import geopandas as gpd
import streamlit as st
import numpy as np
import config
from typing import Tuple, Optional

# --- DATA LOADING ---
@st.cache_data
def load_data(year=None):
    """
    Loads the crime data for a specific year.
    If no year is specified, loads the default year.
    """
    if year is None:
        year = config.DEFAULT_YEAR
        
    if year not in config.DATA_FILES:
        st.error(f"Data for year {year} not found.")
        return pd.DataFrame()

    filename = config.DATA_FILES[year]
    try:
        df = pd.read_csv(filename)
        # Clean column names
        df.columns = df.columns.str.strip().str.replace("\n", " ")
        return df
    except FileNotFoundError:
        st.error(f"File not found: {filename}")
        return pd.DataFrame()

@st.cache_data
def load_all_years():
    """
    Loads data from all configured years and combines them into a single DataFrame.
    Adds a 'Year' column.
    """
    all_data = []
    for year, filename in config.DATA_FILES.items():
        try:
            df = pd.read_csv(filename)
            df.columns = df.columns.str.strip().str.replace("\n", " ")
            df['Year'] = year
            all_data.append(df)
        except FileNotFoundError:
            continue
            
    if not all_data:
        return pd.DataFrame()
        
    return pd.concat(all_data, ignore_index=True)

@st.cache_resource
def load_land_area() -> pd.DataFrame:
    """Loads the land area data from CSV."""
    try:
        land_df = pd.read_csv(config.LAND_AREA_FILE)
        land_df.columns = land_df.columns.str.strip().str.replace("\n", " ")
        return land_df
    except FileNotFoundError:
        st.error(f"File not found: {config.LAND_AREA_FILE}")
        return pd.DataFrame()

@st.cache_resource
def load_places() -> gpd.GeoDataFrame:
    """Loads the shapefile for Texas places."""
    try:
        gdf = gpd.read_file(config.SHAPEFILE)
        # Calculate centroid for mapping
        gdf["centroid"] = gdf.geometry.centroid
        return gdf
    except Exception as e:
        st.error(f"Error loading shapefile: {e}")
        return gpd.GeoDataFrame()

# --- DATA PROCESSING ---
@st.cache_data
def merge_and_process_data(df: pd.DataFrame, land_df: pd.DataFrame) -> pd.DataFrame:
    """Merges crime data with land area and calculates densities."""
    
    # Merge
    if "Agency" in df.columns and "city" in land_df.columns:
        df = df.merge(land_df, how="left", left_on="Agency", right_on="city")
    
    # Calculate population density
    if "Population" in df.columns and "Land Area" in df.columns:
        df["Population Density"] = df["Population"] / df["Land Area"]
    else:
        df["Population Density"] = None
        
    # Calculate crime percentage columns
    for col in df.columns:
        if col not in config.EXCLUDE_COLS and pd.api.types.is_numeric_dtype(df[col]):
            if "Population" in df.columns:
                df[f"{col} %"] = (df[col] / df["Population"]) * 100
                
    return df

def get_city_latlon(name: str, gdf_places: gpd.GeoDataFrame) -> Tuple[Optional[float], Optional[float]]:
    """Finds the latitude and longitude of a city using the shapefile."""
    if gdf_places.empty:
        return None, None
    row = gdf_places[gdf_places["NAME"].str.lower() == name.lower()]
    if not row.empty:
        return row.iloc[0]["centroid"].y, row.iloc[0]["centroid"].x
    else:
        return None, None

def add_coordinates(df: pd.DataFrame, gdf_places: gpd.GeoDataFrame) -> pd.DataFrame:
    """Adds latitude and longitude columns to the dataframe."""
    if gdf_places.empty:
        df["latitude"] = None
        df["longitude"] = None
        return df
        
    df["latitude"] = df["Agency"].apply(lambda x: get_city_latlon(str(x).strip(), gdf_places)[0] if pd.notnull(x) else None)
    df["longitude"] = df["Agency"].apply(lambda x: get_city_latlon(str(x).strip(), gdf_places)[1] if pd.notnull(x) else None)
    return df

# --- PREDICTION ---
def predict_crime_growth(df: pd.DataFrame, crime_col: str, current_pop: int, growth_rate: float = config.DEFAULT_GROWTH_RATE) -> Tuple[Optional[int], Optional[int]]:
    """
    Predicts crime range based on population growth using linear regression.
    Returns (lower_bound, upper_bound).
    """
    if crime_col in df.columns and "Population" in df.columns:
        valid_data = df.dropna(subset=[crime_col, "Population"])
        if len(valid_data) > 1:
            x = valid_data["Population"].values
            y = valid_data[crime_col].values
            
            try:
                slope, intercept = np.polyfit(x, y, 1)
                
                future_pop_lower = current_pop * (1 - growth_rate)
                future_pop_upper = current_pop * (1 + growth_rate)
                
                pred_crime_lower = slope * future_pop_lower + intercept
                pred_crime_upper = slope * future_pop_upper + intercept
                
                return int(max(0, pred_crime_lower)), int(max(0, pred_crime_upper))
            except Exception:
                return None, None
    return None, None
