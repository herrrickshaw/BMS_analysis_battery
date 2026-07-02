#!/usr/bin/env python3
"""Create integrated map: cold chain projects + service outlets."""

import folium
from folium import plugins
import pandas as pd
import json
from pathlib import Path

def get_state_coordinates():
    """State capitals and coordinates for mapping."""
    return {
        'Maharashtra': {'lat': 19.0760, 'lon': 72.8777, 'city': 'Mumbai'},
        'Andhra Pradesh': {'lat': 17.3850, 'lon': 78.4867, 'city': 'Hyderabad'},
        'Gujarat': {'lat': 23.0225, 'lon': 72.5714, 'city': 'Ahmedabad'},
        'Haryana': {'lat': 29.5673, 'lon': 77.0960, 'city': 'Chandigarh'},
        'Himachal Pradesh': {'lat': 31.7046, 'lon': 77.1025, 'city': 'Shimla'},
        'Karnataka': {'lat': 15.2993, 'lon': 75.7541, 'city': 'Bangalore'},
        'Madhya Pradesh': {'lat': 23.1815, 'lon': 79.9864, 'city': 'Bhopal'},
        'Kerala': {'lat': 10.8505, 'lon': 76.2711, 'city': 'Kochi'},
        'Jammu & Kashmir': {'lat': 34.0837, 'lon': 74.7973, 'city': 'Srinagar'},
        'Assam': {'lat': 26.1445, 'lon': 91.7362, 'city': 'Guwahati'},
        'Bihar': {'lat': 25.5941, 'lon': 85.1376, 'city': 'Patna'},
        'Chhattisgarh': {'lat': 21.2787, 'lon': 81.8661, 'city': 'Raipur'},
        'Andaman & Nicobar': {'lat': 11.7401, 'lon': 92.6586, 'city': 'Port Blair'},
        'Arunachal Pradesh': {'lat': 28.2180, 'lon': 94.2037, 'city': 'Itanagar'},
    }

def create_cold_chain_outlet_map():
    """Create integrated visualization map."""
    print("\n" + "="*80)
    print("🗺️  CREATING INTEGRATED COLD CHAIN + OUTLET MAP")
    print("="*80)

    # Cold chain data
    cold_chain_data = {
        'Maharashtra': {'projects': 62, 'capacity': 103.38, 'sectors': 'FAV, Dairy, Fishery'},
        'Andhra Pradesh': {'projects': 32, 'capacity': 270.32, 'sectors': 'Fishery, Dairy, FAV'},
        'Gujarat': {'projects': 27, 'capacity': 252.97, 'sectors': 'FAV, Dairy'},
        'Haryana': {'projects': 20, 'capacity': 143.73, 'sectors': 'FAV, Irrigation'},
        'Himachal Pradesh': {'projects': 17, 'capacity': 148.71, 'sectors': 'FAV, Dairy'},
        'Karnataka': {'projects': 16, 'capacity': 131.38, 'sectors': 'FAV, Dairy, Meat'},
        'Madhya Pradesh': {'projects': 13, 'capacity': 103.38, 'sectors': 'FAV, Irrigation'},
        'Kerala': {'projects': 6, 'capacity': 42.35, 'sectors': 'Dairy, Fishery'},
        'Jammu & Kashmir': {'projects': 7, 'capacity': 52.83, 'sectors': 'FAV, Dairy'},
        'Assam': {'projects': 2, 'capacity': 17.37, 'sectors': 'FAV'},
        'Bihar': {'projects': 6, 'capacity': 48.95, 'sectors': 'Dairy, FAV'},
        'Chhattisgarh': {'projects': 2, 'capacity': 11.50, 'sectors': 'FAV'},
        'Andaman & Nicobar': {'projects': 2, 'capacity': 12.86, 'sectors': 'Fishery'},
        'Arunachal Pradesh': {'projects': 1, 'capacity': 6.46, 'sectors': 'Meat'},
    }

    # Outlet data summary
    outlet_data = {
        'Maharashtra': 62, 'Andhra Pradesh': 14, 'Gujarat': 18, 'Haryana': 15,
        'Himachal Pradesh': 1, 'Karnataka': 4, 'Uttar Pradesh': 169, 'West Bengal': 116,
        'Madhya Pradesh': 64, 'Punjab': 48, 'Odisha': 34, 'Tamil Nadu': 34, 'Assam': 0
    }

    # Create base map (India center)
    m = folium.Map(
        location=[20.5937, 78.9629],
        zoom_start=5,
        tiles='OpenStreetMap'
    )

    coords = get_state_coordinates()

    # Add markers for cold chains and outlets
    for state, cc_data in cold_chain_data.items():
        if state in coords:
            coord = coords[state]
            outlets = outlet_data.get(state, 0)

            # Circle size based on cold chain capacity
            radius = cc_data['capacity'] * 100
            color = 'blue' if cc_data['projects'] > 30 else 'cyan'

            # Popup with detailed info
            popup_text = f"""
            <b>{state}</b><br>
            <b>Cold Chain Projects:</b> {cc_data['projects']}<br>
            <b>Capacity:</b> {cc_data['capacity']:.2f} MT<br>
            <b>Sectors:</b> {cc_data['sectors']}<br>
            <b>Service Outlets (Cash@PoS):</b> {outlets}
            """

            folium.Circle(
                location=[coord['lat'], coord['lon']],
                radius=radius,
                popup=folium.Popup(popup_text, max_width=300),
                color=color,
                fill=True,
                fillColor=color,
                fillOpacity=0.3,
                weight=2
            ).add_to(m)

            # Add marker
            icon_color = 'darkblue' if cc_data['projects'] > 30 else 'blue'
            folium.Marker(
                location=[coord['lat'], coord['lon']],
                popup=f"{state}<br>{cc_data['projects']} projects",
                tooltip=f"{state}: {cc_data['projects']} cold chain projects",
                icon=folium.Icon(color=icon_color, icon='info-sign')
            ).add_to(m)

    # Add legend
    legend_html = '''
    <div style="position: fixed;
                bottom: 50px; right: 50px; width: 300px; height: auto;
                background-color: white; border:2px solid grey; z-index:9999;
                font-size:14px; padding: 10px">
    <p style="margin: 0 0 10px 0"><b>Cold Chain + Outlet Integration Map</b></p>
    <p><i class="fa fa-circle" style="color:blue"></i> Cold Chain Projects & Capacity</p>
    <p><i class="fa fa-marker" style="color:darkblue"></i> Top States (>30 projects)</p>
    <p style="font-size: 12px; margin-top: 10px">
    <b>Circle size:</b> Project capacity (MT)<br>
    <b>Circle color:</b> Project density<br>
    <b>Blue:</b> High capacity regions
    </p>
    <p style="font-size: 12px; margin-top: 10px; color: #666;">
    📊 357 total cold chain projects<br>
    🏪 104,961 SSRI petrol pumps<br>
    🛢️ 693 Cash@PoS outlets extracted
    </p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))

    # Save map
    output_file = 'cold_chain_outlet_integrated_map.html'
    m.save(output_file)

    print(f"\n✅ Map created: {output_file}")
    print(f"   Coverage: 14 states with cold chain projects")
    print(f"   Integration: Cold chains + 693 Cash@PoS outlets")
    print(f"   Total capacity: 1,346.19 MT across India")

    return output_file

def create_supply_chain_analysis():
    """Analyze supply chain corridors."""
    print("\n" + "="*80)
    print("📊 SUPPLY CHAIN CORRIDOR ANALYSIS")
    print("="*80)

    analysis = {
        'Eastern Corridor': {
            'states': ['Assam', 'West Bengal', 'Bihar', 'Odisha'],
            'cold_chains': 10,
            'outlets': 214,
            'primary_sectors': ['Dairy', 'Fishery', 'FAV'],
            'logistics_route': 'Eastern coast, inland waterways'
        },
        'Western Corridor': {
            'states': ['Gujarat', 'Maharashtra', 'Goa'],
            'cold_chains': 89,
            'outlets': 80,
            'primary_sectors': ['Fishery', 'FAV', 'Dairy'],
            'logistics_route': 'Arabian sea ports, NH-48'
        },
        'Southern Corridor': {
            'states': ['Karnataka', 'Kerala', 'Tamil Nadu', 'Andhra Pradesh'],
            'cold_chains': 54,
            'outlets': 68,
            'primary_sectors': ['Fishery', 'Dairy', 'FAV'],
            'logistics_route': 'Bay of Bengal, Chennai-Bangalore route'
        },
        'Northern Corridor': {
            'states': ['Haryana', 'Himachal Pradesh', 'Jammu & Kashmir', 'Punjab'],
            'cold_chains': 44,
            'outlets': 95,
            'primary_sectors': ['Dairy', 'FAV', 'Fruits'],
            'logistics_route': 'NH-1 (Delhi-Amritsar), Himalayan routes'
        },
        'Central Corridor': {
            'states': ['Madhya Pradesh', 'Chhattisgarh'],
            'cold_chains': 15,
            'outlets': 68,
            'primary_sectors': ['FAV', 'Irrigation'],
            'logistics_route': 'Central India agricultural zones'
        }
    }

    for corridor, data in analysis.items():
        print(f"\n🛣️  {corridor}")
        print(f"   States: {', '.join(data['states'])}")
        print(f"   Cold Chains: {data['cold_chains']}")
        print(f"   Service Outlets: {data['outlets']}")
        print(f"   Sectors: {', '.join(data['primary_sectors'])}")
        print(f"   Route: {data['logistics_route']}")

    return analysis

if __name__ == "__main__":
    map_file = create_cold_chain_outlet_map()
    corridors = create_supply_chain_analysis()

    print("\n" + "="*80)
    print("✨ INTEGRATION SUMMARY")
    print("="*80)
    print("\n📍 Geographic Data Points:")
    print(f"   - 14 states with cold chain infrastructure")
    print(f"   - 357 approved cold chain projects")
    print(f"   - 104,961 SSRI petrol pumps (baseline)")
    print(f"   - 693 extracted Cash@PoS/ATM outlets")
    print(f"   - 5 major supply chain corridors")
    print(f"\n💡 Key Insights:")
    print(f"   - Maharashtra: 62 cold chains, 62 outlets")
    print(f"   - Andhra Pradesh: 32 cold chains (270 MT capacity)")
    print(f"   - Eastern corridor: 214 outlets, 10 cold chains")
    print(f"   - Western corridor: 89 cold chains (highest)")
    print("\n" + "="*80 + "\n")
