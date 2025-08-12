# -*- coding: utf-8 -*-
"""
Created on Mon Dec 18 14:32:06 2023
Program som tar et koordinat (EPSG:32633 – WGS 84 / UTM zone 33N) og en eksplosivmengde og finner alle bygninger innenfor hensynssonen.
@author: KRHE
"""

import pandas as pd
import geopandas as gpd
import folium
import numpy as np
import requests
import streamlit as st
from io import BytesIO

# st.set_page_config(layout="wide") #wide mode

from streamlit_folium import st_folium
from amr25filecreator import generate_amrisk_base_file, generate_exposed_objects
from get_veg_data import get_veg_data
from get_matrikkel_data import get_matrikkel_data

output = pd.DataFrame()
output_csv = pd.DataFrame()
bygningstype_url = 'https://raw.githubusercontent.com/Freeyolo/tangos/main/bygningstype.csv'
   


def QD_func(NEI):
    """denne funksjonen tar netto eksplosivinnhold (NEI) som argument og returnerer sikkerhetsavstanden 
    (QD, Quantity Distance) for hhv. sykehus, bolig og vei. QD er definert i eksplosivforskriften § 37"""

    QD_syk = max(round(44.4 * NEI ** (1/3)), 800)
    QD_bolig = max(round(22.2 * NEI ** (1/3)), 400)
    QD_vei = max(round(14.8 * NEI ** (1/3)), 180)
    return QD_syk, QD_bolig, QD_vei

def incident_pressure(D):
    """Create a function that uses the scaled distance (Z) to calculate the incident 
    pressure in kPa from the simplified Kingery & Bulmash polynomials
    provided by Swisdak, M. in 1994 the input is the distance and net eksplosive content (NEI) in TNT equivalents
    returns pressure in kPa"""

    Z = D/NEI**(1/3) #scaled distance

    if Z <= 2.9:
        Az = 7.2106
        Bz = -2.1069
        Cz = -0.3229
        Dz = 0.1117
        Ez = 0.0685
    elif Z <= 23.8:
        Az = 7.5938
        Bz = -3.0523
        Cz = 0.40977
        Dz = 0.0261
        Ez = -0.01267
    elif Z > 23.8:
        Az = 6.0536
        Bz = -1.4066
        Cz = 0
        Dz = 0
        Ez = 0
    return (np.exp(Az+Bz*np.log(Z) + Cz * (np.log(Z))**2+ Dz * (np.log(Z))**3+ Ez * (np.log(Z))**4))

tab1, tab2 = st.tabs(['Input','Amrisk'])

# =============================================================================
# TAB 1 – Input, beregninger og kart
# =============================================================================

with tab1:
    with st.form("my_form"):
       st.write("Input data")
       nording = st.number_input('Nording / Y', value=None, step=1, placeholder='EPSG:32633 - WGS 84 / UTM zone 33N')
       oesting = st.number_input('Østing / X', value=None, step=1, placeholder='EPSG:32633 - WGS 84 / UTM zone 33N')
       NEI = st.number_input('Totalvekt', value=None, step=1, min_value=1, max_value=100000, placeholder='Netto eksplosivinnhold (NEI) i kg')
       st.session_state["last_inputs"] = {"oesting": oesting, "nording": nording, "NEI": NEI}
       
       # Every form must have a submit button.
       submitted = st.form_submit_button("Submit")
       if submitted:
        d = {'nording':[nording],'oesting':[oesting],'NEI':[NEI]}
        df = pd.DataFrame(data=d)
        gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.oesting,df.nording),crs='EPSG:32633')
           
        QD_syk, QD_bolig, QD_vei = QD_func(NEI)
    
        #en geopandas geodataframe kan kun ha en "geometry" kolonne, derfor er det nødvendig å kopiere gdf tre ganger
    
        gdf_syk = gdf.copy().drop(columns=['nording','oesting'])
        gdf_bolig = gdf.copy().drop(columns=['nording','oesting'])
        gdf_vei = gdf.copy().drop(columns=['nording','oesting'])
    
        gdf_syk['QD_syk'] = QD_syk
        gdf_syk['trykk'] = '2 kPa' #trykket som korresponderer til QD avstanden, kun for visualisering
    
        gdf_bolig['QD_bolig'] = QD_bolig
        gdf_bolig['trykk'] = '5 kPa'
    
        gdf_vei['QD_vei'] = QD_vei
        gdf_vei['trykk'] = '9 kPa'
        
        gdf_syk['geometry'] = gdf_syk['geometry'].buffer(gdf_syk['QD_syk'])  
        gdf_bolig['geometry'] = gdf_bolig['geometry'].buffer(gdf_bolig['QD_bolig'])
        gdf_vei['geometry'] = gdf_vei['geometry'].buffer(gdf_vei['QD_vei'])
        
        #dette er kartpunktet for lageret
        kartpunkt = gdf.explore(marker_type=folium.Marker(icon=folium.Icon(color='blue', icon='bomb', prefix='fa')),name='anlegg',control=False)
        
        # Lage en firkantet bounding boks for QD_syk, denne vil også inneholde QD_bolig og QD_vei
        gdf_syk_bbox = pd.concat([gdf_syk, gdf_syk['geometry'].bounds], axis=1) #lager en firkantet bounding box for de sirkulære sikkerhetsavstandene
        gdf_vei_bbox = pd.concat([gdf_vei, gdf_vei['geometry'].bounds], axis=1) #lager en firkantet bounding box for de sirkulære sikkerhetsavstandene  
        
        #dataframe med boliger innenfor sikkerhetsavstandene
        result_geodataframe = get_matrikkel_data(gdf_syk_bbox.iloc[0])
    
        #dataframe med vegsegmenter som har ÅDT innenfor sikkerhetsavstandene       
        result_veg_geodataframe = get_veg_data(gdf_vei_bbox.iloc[0])
    
        if not result_veg_geodataframe.empty:
            vegsegmenter = result_veg_geodataframe.explode(ignore_index=True)
            vegsegmenter.crs = 'EPSG:32633'
            kart_veg = vegsegmenter.explore(m=kartpunkt,style_kwds=dict(color='black'), name="Vei")
    
        if not result_geodataframe.empty:
            eksponerte_bygg_syk = gpd.sjoin(result_geodataframe, gdf_syk, predicate='within') #behold bare bygninger innenfor sirkelen
            output = eksponerte_bygg_syk[['bygningstype', 'geometry']] #kun interessant med disse kolonnene for videre visualisering
            
            bygningstype = pd.read_csv(bygningstype_url, index_col=False, sep=';', usecols=['Navn', 'Kodeverdi'], encoding='utf8') #last in bygningstype fra SSB
            output = output.merge(bygningstype, how='left', left_on='bygningstype', right_on='Kodeverdi') #få på leselige navn på bygningstype
            output.drop(columns=['Kodeverdi'], inplace=True) #fjern unødvendig kolonne
    
            output['avstand m'] = round(output.distance(gdf.iloc[0]['geometry'])) #regn ut avstanden til eksplosivlageret
            output['trykk kPa'] = output['avstand m'].apply(incident_pressure).round(2) #regner ut trykket og runder av til to desimaler
    
            output['bygningstype'] = output['bygningstype'].astype(str) # Convert 'bygningstype' column to string type
            boliger = output[output['bygningstype'].str.startswith('1')]
            industri = output[output['bygningstype'].str.startswith('2')]
            kontor = output[output['bygningstype'].str.startswith('3')]
            samferdsel = output[output['bygningstype'].str.startswith('4')]
            hotell = output[output['bygningstype'].str.startswith('5')]
            kultur = output[output['bygningstype'].str.startswith('6')]
            helse = output[output['bygningstype'].str.startswith('7')]
            brann = output[output['bygningstype'].str.startswith('8')]
            annet = output[output['bygningstype'].str.startswith('9')]
            output_csv = pd.DataFrame(output)  # convert back to pandas dataframe
            output_csv["geometry"] = output_csv["geometry"].astype(str)
            st.session_state['output_csv'] = output_csv
            # =============================================================================
            # Plotting av matrikkeldata i kart og lagring av kartet
            # =============================================================================
            kartQDsyk = gdf_syk.explore(m=kartpunkt,style_kwds=dict(fill=False,color='red'),name ='QDsyk',control=False)
            kartQDbol = gdf_bolig.explore(m=kartpunkt,style_kwds=dict(fill=False,color='orange'),name ='QDbolig',control=False)
            kartQDvei = gdf_vei.explore(m=kartpunkt,style_kwds=dict(fill=False,color='black'),name ='QDvei',control=False)
    
            if not industri.empty:
                kartindustri = industri.explore(m=kartpunkt, style_kwds=dict(color='black'), name="Industri/lager")
            if not kontor.empty:
                kartkontor = kontor.explore(m=kartpunkt, style_kwds=dict(color='black'), name="Kontor/forretning")
            if not samferdsel.empty:
                kartsamferdsel = samferdsel.explore(m=kartpunkt, style_kwds=dict(color='black'), name="Samferdsel")
            if not hotell.empty:
                karthotell = hotell.explore(m=kartpunkt, style_kwds=dict(color='red'), name="Hotell/restaurant")
            if not kultur.empty:
                kartkultur = kultur.explore(m=kartpunkt, style_kwds=dict(color='red'), name="Skole/bhg/idrett")
            if not helse.empty:
                karthelse = helse.explore(m=kartpunkt, style_kwds=dict(color='red'), name="Helse")
            if not brann.empty:
                kartbrann = brann.explore(m=kartpunkt, style_kwds=dict(color='red'), name="Brann/politi")
            if not annet.empty:
                kartannet = annet.explore(m=kartpunkt, style_kwds=dict(color='black'), name="Annet")
            if not boliger.empty:
                kartboliger = boliger.explore(m=kartpunkt, style_kwds=dict(color='orange'), name="Boliger")
    
            folium.LayerControl().add_to(kartpunkt)
            st_kart = st_folium(kartpunkt,width=672,zoom=13)
              
        else:
            output_csv = pd.DataFrame()
            st.write('Ingen bygninger eksponert :sunglasses:')
            # =============================================================================
            # kart uten utsatte objekter
            # =============================================================================
            kartQDsyk = gdf_syk.explore(m=kartpunkt,style_kwds=dict(fill=False,color='red'),name ='QDsyk',control=False)
            kartQDbol = gdf_bolig.explore(m=kartpunkt,style_kwds=dict(fill=False,color='orange'),name ='QDbolig',control=False)
            kartQDvei = gdf_vei.explore(m=kartpunkt,style_kwds=dict(fill=False,color='black'),name ='QDvei',control=False)
            st_kart = st_folium(kartpunkt,width=672,zoom=13)
     
    # =============================================================================
    # Eksportering av data i CSV format
    # =============================================================================
    
    @st.cache_data
    def convert_df(dinn):
    # IMPORTANT: Cache the conversion to prevent computation on every rerun
        return dinn.to_csv().encode('utf-8-sig')
    csv = convert_df(output_csv)
 
    st.download_button(
       label="Download data as CSV",
       data=csv,
       file_name='eksponerte_bygg.csv',
       on_click="ignore",
       mime='text/csv',
       icon=":material/download:",
       )
    
    
# =============================================================================
# TAB 2 – AMRISK: parametre, generering og eksport
# =============================================================================

    

with tab2:
    if (st.session_state.get("last_inputs") and st.session_state.get("last_inputs").get("NEI")) is None:
        st.warning("Fyll inn data i fanen 'Input' først og kjør beregning.")
        st.stop()
    if st.button('Generer AMRISK-fil'):
        if None in (oesting, nording, NEI):
            st.warning("Mangler input eller ingen eksponerte bygg")
        else:
            base = generate_amrisk_base_file(coord_x=oesting, coord_y=nording, charge_kg=NEI)
            objects = generate_exposed_objects(st.session_state['output_csv'])
            st.session_state['amrisk_file'] = base + "\n" + objects
            st.success("Fil generert")
            
    if 'amrisk_file' in st.session_state:    
        st.download_button(
           label="Export AMRISK2.5 file",
           data=st.session_state['amrisk_file'].encode("utf-8"),
           file_name="amrisk_export.amr25",
           on_click="ignore",
           mime='text/csv',
           icon=":material/download:",
           )