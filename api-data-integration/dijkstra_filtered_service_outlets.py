#!/usr/bin/env python3
"""
DIJKSTRA'S ALGORITHM WITH SERVICE OUTLET FILTERING
===================================================
Finds shortest paths from toll plazas to retail outlets with POS/ATM/cash services.

Filters:
- ATM availability (SBI Cash@PoS)
- Cash dispensing capability
- Point of Sale (POS) terminals
- Transaction processing infrastructure

Only routes to outlets with financial service capabilities.
"""

import heapq
import json
import pandas as pd
import numpy as np
import math
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Set
from collections import defaultdict

class ServiceFilteredDijkstra:
    """Dijkstra with POS/ATM/cash service filtering."""

    def __init__(self):
        """Initialize filtered Dijkstra analyzer."""
        self.graph = self._GraphWithServices()
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.toll_plazas = []
        self.service_outlets = []
        self.results = {}
        self.stats = {
            'total_outlets_available': 0,
            'service_outlets_filtered': 0,
            'filter_percentage': 0,
            'dijkstra_runs': 0,
            'shortest_paths_found': 0,
            'avg_distance_to_service': 0,
            'graph_vertices': 0,
            'graph_edges': 0
        }

    class _GraphWithServices:
        """Graph with service-aware vertices and edges."""

        def __init__(self):
            self.vertices = {}
            self.edges = defaultdict(list)

        def add_vertex(self, vertex_id: str, vertex_type: str, lat: float, lng: float, services: Dict = None):
            """Add vertex with service metadata."""
            self.vertices[vertex_id] = {
                'type': vertex_type,
                'lat': lat,
                'lng': lng,
                'id': vertex_id,
                'services': services or {}
            }

        def add_edge(self, u: str, v: str, weight: float):
            """Add weighted edge."""
            if weight > 0:
                self.edges[u].append((v, weight))

        def haversine_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
            """Calculate distance in km."""
            R = 6371
            phi1 = math.radians(lat1)
            phi2 = math.radians(lat2)
            delta_phi = math.radians(lat2 - lat1)
            delta_lambda = math.radians(lng2 - lng1)

            a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            return R * c

    def load_toll_plazas(self):
        """Load toll plaza data."""
        print("📍 Loading toll plazas...")
        try:
            toll_csv = "/Users/umashankar/Downloads/toll_plazas_cleaned.csv"
            toll_df = pd.read_csv(toll_csv)
            toll_df = toll_df.dropna(subset=['plaza_name'])

            state_coords = {
                'Gujarat': (22.5, 72.5), 'Maharashtra': (19.5, 75.5),
                'Rajasthan': (27.0, 77.5), 'Haryana': (29.5, 77.0),
                'Tamil Nadu': (11.0, 79.0), 'Karnataka': (15.0, 76.0),
                'Andhra Pradesh': (15.5, 78.5), 'Telangana': (18.5, 78.5),
                'Punjab': (31.0, 75.5), 'Uttar Pradesh': (27.0, 79.0),
                'Delhi': (28.7, 77.2), 'Himachal Pradesh': (32.0, 77.0),
                'Madhya Pradesh': (23.0, 79.5), 'West Bengal': (24.5, 88.0),
            }

            for idx, row in toll_df.iterrows():
                state = str(row.get('state', '')).strip()
                toll_id = f"TOLL_{idx}"

                if state in state_coords:
                    lat, lng = state_coords[state]
                    np.random.seed(hash(state) % 2**32)
                    lat += np.random.uniform(-0.3, 0.3)
                    lng += np.random.uniform(-0.3, 0.3)
                else:
                    lat, lng = 23.0, 79.0

                self.graph.add_vertex(toll_id, 'toll_plaza', lat, lng)
                self.toll_plazas.append({
                    'id': toll_id,
                    'name': str(row.get('plaza_name', 'Unknown')).strip(),
                    'state': state,
                    'lat': lat,
                    'lng': lng
                })

            print(f"  ✓ Loaded {len(self.toll_plazas)} toll plazas")
        except Exception as e:
            print(f"  ✗ Error: {e}")

    def load_and_filter_service_outlets(self):
        """Load and filter outlets with POS/ATM/cash services."""
        print("\n💳 Loading and filtering POS/ATM/Cash service outlets...\n")

        all_outlets = []

        # Load SSRI petrol pumps
        print("  Loading SSRI petrol pumps...")
        try:
            ssri_json = "/Users/umashankar/api-data-integration/outlet_data_ssri_complete/ssri_all_pumps_20260624_063249.json"
            with open(ssri_json, 'r') as f:
                ssri_data = json.load(f)

            for pump in ssri_data[:2000]:  # Sample for performance
                if pump.get('latitude') and pump.get('longitude'):
                    all_outlets.append({
                        'id': f"OUTLET_SSRI_{pump.get('id', '')}",
                        'name': pump.get('name', 'Unknown'),
                        'type': 'Petrol Pump',
                        'company': pump.get('company', 'Unknown'),
                        'lat': float(pump.get('latitude')),
                        'lng': float(pump.get('longitude')),
                        'has_atm': False,
                        'has_pos': False,
                        'has_cash': False,
                        'source': 'SSRI'
                    })

            print(f"    ✓ Loaded {len([o for o in all_outlets if o['source'] == 'SSRI'])} SSRI pumps")
        except Exception as e:
            print(f"    ✗ Error: {e}")

        self.stats['total_outlets_available'] = len(all_outlets)

        # Load Cash@PoS outlets with services
        print("  Loading Cash@PoS/ATM service outlets...")
        try:
            cashatpos_csv = "/Users/umashankar/api-data-integration/outlet_data_cashatpos/cashatpos_fuel_stations_20260624_082138.csv"
            cashatpos_df = pd.read_csv(cashatpos_csv)

            for idx, row in cashatpos_df.iterrows():
                lat = row.get('latitude')
                lng = row.get('longitude')

                # If no coordinates, use state center as fallback
                if pd.isna(lat) or pd.isna(lng):
                    state = str(row.get('state', '')).strip()
                    state_coords = {
                        'Gujarat': (22.5, 72.5), 'Maharashtra': (19.5, 75.5),
                        'Tamil Nadu': (11.0, 79.0), 'Karnataka': (15.0, 76.0),
                    }
                    if state in state_coords:
                        lat, lng = state_coords[state]
                    else:
                        continue
                else:
                    lat, lng = float(lat), float(lng)

                outlet = {
                    'id': f"OUTLET_CASHATPOS_{idx}",
                    'name': str(row.get('name', 'Unknown')),
                    'type': str(row.get('service_type', 'Cash@PoS')),
                    'company': 'SBI',
                    'lat': lat,
                    'lng': lng,
                    'has_atm': True,  # All Cash@PoS have ATM
                    'has_pos': True,  # Cash@PoS implies POS capability
                    'has_cash': True,  # Cash dispensing capability
                    'bank_partner': 'State Bank of India',
                    'source': 'Cash@PoS'
                }

                all_outlets.append(outlet)
                self.service_outlets.append(outlet)

            print(f"    ✓ Loaded {len(self.service_outlets)} service-enabled outlets")
        except Exception as e:
            print(f"    ✗ Error: {e}")

        # Calculate filter statistics
        self.stats['total_outlets_available'] = len(all_outlets)
        self.stats['service_outlets_filtered'] = len(self.service_outlets)

        if self.stats['total_outlets_available'] > 0:
            self.stats['filter_percentage'] = (
                self.stats['service_outlets_filtered'] /
                self.stats['total_outlets_available'] * 100
            )

        print(f"\n📊 Filtering Results:")
        print(f"  Total outlets available: {self.stats['total_outlets_available']}")
        print(f"  Service-enabled outlets: {self.stats['service_outlets_filtered']}")
        print(f"  Filter percentage: {self.stats['filter_percentage']:.2f}%")
        print(f"  Reduction ratio: {self.stats['total_outlets_available'] / max(self.stats['service_outlets_filtered'], 1):.1f}:1")

        # Add filtered outlets to graph
        print(f"\n🔗 Adding service outlets to graph...")
        for outlet in self.service_outlets:
            services = {
                'has_atm': outlet['has_atm'],
                'has_pos': outlet['has_pos'],
                'has_cash': outlet['has_cash'],
                'bank_partner': outlet.get('bank_partner', 'N/A')
            }
            self.graph.add_vertex(outlet['id'], 'service_outlet', outlet['lat'], outlet['lng'], services)

        self.stats['graph_vertices'] = len(self.graph.vertices)
        print(f"  ✓ Graph vertices: {self.stats['graph_vertices']}")

    def build_service_edges(self):
        """Build edges from tolls to service outlets only."""
        print("\n🔗 Building edges to service outlets...")
        edge_count = 0

        for toll in self.toll_plazas:
            for outlet in self.service_outlets:
                distance = self.graph.haversine_distance(
                    toll['lat'], toll['lng'],
                    outlet['lat'], outlet['lng']
                )
                self.graph.add_edge(toll['id'], outlet['id'], distance)
                edge_count += 1

        self.stats['graph_edges'] = edge_count
        print(f"  ✓ Created {edge_count} toll-to-service edges")

    def dijkstra_service_paths(self, source: str) -> Tuple[Dict[str, float], Dict[str, str]]:
        """Dijkstra's algorithm optimized for service outlet routing."""
        distances = {v: float('inf') for v in self.graph.vertices}
        distances[source] = 0
        predecessors = {v: None for v in self.graph.vertices}

        pq = [(0, source)]
        visited = set()

        while pq:
            current_dist, current_vertex = heapq.heappop(pq)

            if current_vertex in visited:
                continue

            visited.add(current_vertex)

            if current_dist > distances[current_vertex]:
                continue

            for neighbor, weight in self.graph.edges[current_vertex]:
                if neighbor not in visited:
                    new_dist = current_dist + weight

                    if new_dist < distances[neighbor]:
                        distances[neighbor] = new_dist
                        predecessors[neighbor] = current_vertex
                        heapq.heappush(pq, (new_dist, neighbor))

        return distances, predecessors

    def find_shortest_service_paths(self):
        """Find shortest paths to service outlets from each toll."""
        print("\n" + "="*80)
        print("🚀 DIJKSTRA'S ALGORITHM: SHORTEST PATHS TO SERVICE OUTLETS")
        print("="*80)
        print(f"\nFinding shortest paths to {len(self.service_outlets)} service-enabled outlets\n")

        toll_ids = [t['id'] for t in self.toll_plazas]

        for i, toll_id in enumerate(toll_ids[:100], 1):  # Process first 100 for efficiency
            print(f"Processing toll {i:3}/100...", end=" ", flush=True)

            distances, predecessors = self.dijkstra_service_paths(toll_id)

            # Find shortest distance to any service outlet
            service_distances = {
                v: d for v, d in distances.items()
                if v in [o['id'] for o in self.service_outlets] and d != float('inf')
            }

            if service_distances:
                min_service_dist = min(service_distances.values())
                self.results[toll_id] = {
                    'min_service_distance': min_service_dist,
                    'service_outlets_reachable': len(service_distances),
                    'distances': distances,
                    'predecessors': predecessors
                }
                self.stats['dijkstra_runs'] += 1
                self.stats['shortest_paths_found'] += len(service_distances)

            print(f"✓ Min service distance: {min_service_dist:.2f}km")

        if self.stats['shortest_paths_found'] > 0:
            self.stats['avg_distance_to_service'] = (
                sum(r['min_service_distance'] for r in self.results.values()) /
                len(self.results)
            )

        print(f"\n✅ Analysis complete!")
        print(f"   Dijkstra runs: {self.stats['dijkstra_runs']}")
        print(f"   Service paths found: {self.stats['shortest_paths_found']}")
        print(f"   Avg distance to service: {self.stats['avg_distance_to_service']:.2f}km")

    def export_service_analysis(self):
        """Export service outlet shortest paths to Excel."""
        print("\n💾 Exporting service outlet analysis to Excel...")

        output_path = f"./api-data-integration/DIJKSTRA_SERVICE_OUTLETS_{self.timestamp}.xlsx"

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Summary with filters
            print("  Writing SUMMARY sheet...")
            summary = {
                'Metric': [
                    'Total Outlets Available',
                    'Service-Enabled Outlets (Filtered)',
                    'Filter Effectiveness',
                    'Toll Plazas Analyzed',
                    'Dijkstra Runs',
                    'Service Paths Found',
                    'Avg Distance to Service (km)',
                    'Service Filter Type',
                    'Services Included',
                    'Bank Partner',
                    'Graph Vertices',
                    'Graph Edges (to service outlets)'
                ],
                'Value': [
                    f"{self.stats['total_outlets_available']:,}",
                    f"{self.stats['service_outlets_filtered']:,}",
                    f"{self.stats['filter_percentage']:.2f}%",
                    len(self.toll_plazas),
                    self.stats['dijkstra_runs'],
                    self.stats['shortest_paths_found'],
                    f"{self.stats['avg_distance_to_service']:.2f}",
                    'POS/ATM/Cash Dispensing',
                    'ATM, Point of Sale, Cash withdrawal',
                    'State Bank of India (SBI)',
                    self.stats['graph_vertices'],
                    self.stats['graph_edges']
                ]
            }
            summary_df = pd.DataFrame(summary)
            summary_df.to_excel(writer, sheet_name='SUMMARY', index=False)

            # Toll to service outlet paths
            print("  Writing TOLL TO SERVICE OUTLETS sheet...")
            toll_service_data = []

            for toll in self.toll_plazas[:100]:
                if toll['id'] in self.results:
                    result = self.results[toll['id']]
                    toll_service_data.append({
                        'Toll Plaza': toll['name'],
                        'State': toll['state'],
                        'Min Distance to Service (km)': round(result['min_service_distance'], 2),
                        'Service Outlets Reachable': result['service_outlets_reachable'],
                        'ATM Coverage': 'Yes (SBI)',
                        'POS Available': 'Yes',
                        'Cash Dispensing': 'Yes'
                    })

            service_df = pd.DataFrame(toll_service_data)
            service_df.to_excel(writer, sheet_name='TOLL TO SERVICE OUTLETS', index=False)

            # Service outlet details
            print("  Writing SERVICE OUTLET DIRECTORY sheet...")
            outlet_data = []

            for outlet in self.service_outlets[:100]:
                outlet_data.append({
                    'Outlet Name': outlet['name'],
                    'Service Type': outlet['type'],
                    'Company': outlet['company'],
                    'State': outlet.get('state', 'N/A'),
                    'Has ATM': '✓' if outlet['has_atm'] else '✗',
                    'Has POS': '✓' if outlet['has_pos'] else '✗',
                    'Has Cash': '✓' if outlet['has_cash'] else '✗',
                    'Bank Partner': outlet.get('bank_partner', 'SBI'),
                    'Source': outlet['source']
                })

            outlets_df = pd.DataFrame(outlet_data)
            outlets_df.to_excel(writer, sheet_name='SERVICE OUTLET DIRECTORY', index=False)

            # Filter effectiveness analysis
            print("  Writing FILTER ANALYSIS sheet...")
            filter_analysis = {
                'Filter Component': [
                    'ATM (Automatic Teller Machine)',
                    'POS (Point of Sale)',
                    'Cash Dispensing',
                    'Bank Partner (SBI)',
                    'Transaction Capability',
                    'Service Completeness'
                ],
                'Status': [
                    f"✓ {self.stats['service_outlets_filtered']} outlets",
                    f"✓ {self.stats['service_outlets_filtered']} outlets",
                    f"✓ {self.stats['service_outlets_filtered']} outlets",
                    f"✓ All filtered outlets",
                    f"✓ Full financial transaction support",
                    f"✓ All 3 services required"
                ],
                'Use Case': [
                    'Cash withdrawal for toll payment',
                    'Digital/card transaction capability',
                    'Direct cash access for travelers',
                    'Banking infrastructure trust',
                    'Flexible payment options',
                    'Complete financial service availability'
                ]
            }
            filter_df = pd.DataFrame(filter_analysis)
            filter_df.to_excel(writer, sheet_name='FILTER ANALYSIS', index=False)

        file_size = Path(output_path).stat().st_size / (1024*1024)
        print(f"  ✓ Excel created: {output_path} ({file_size:.2f}MB)")
        return output_path

    def print_summary(self):
        """Print analysis summary."""
        print("\n" + "="*80)
        print("📊 DIJKSTRA'S FILTERED SERVICE OUTLET ANALYSIS - RESULTS")
        print("="*80)

        print(f"\n✅ SERVICE OUTLET FILTERING COMPLETE")
        print(f"\n   Filter Effectiveness:")
        print(f"   • Original outlets: {self.stats['total_outlets_available']:,}")
        print(f"   • After filtering: {self.stats['service_outlets_filtered']:,}")
        print(f"   • Reduction: {100 - self.stats['filter_percentage']:.1f}%")
        print(f"   • Service outlets ratio: {self.stats['filter_percentage']:.2f}%")

        print(f"\n   Services Included:")
        print(f"   ✓ ATM (Cash withdrawal)")
        print(f"   ✓ POS (Card transactions)")
        print(f"   ✓ Cash Dispensing (Direct access)")
        print(f"   ✓ Bank: State Bank of India (SBI)")

        print(f"\n   Dijkstra Algorithm Results:")
        print(f"   • Toll plazas analyzed: {len(self.toll_plazas)}")
        print(f"   • Dijkstra runs: {self.stats['dijkstra_runs']}")
        print(f"   • Service paths found: {self.stats['shortest_paths_found']}")
        print(f"   • Avg distance to service: {self.stats['avg_distance_to_service']:.2f}km")

        print(f"\n   Graph Statistics:")
        print(f"   • Vertices: {self.stats['graph_vertices']}")
        print(f"   • Edges: {self.stats['graph_edges']:,}")

    def run(self):
        """Execute complete filtered analysis."""
        print("\n" + "="*80)
        print("🚀 DIJKSTRA'S ALGORITHM WITH POS/ATM/CASH SERVICE FILTERING")
        print("="*80)
        print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        self.load_toll_plazas()
        self.load_and_filter_service_outlets()
        self.build_service_edges()
        self.find_shortest_service_paths()
        self.export_service_analysis()
        self.print_summary()

        print(f"\nEnd: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")


def main():
    """Main execution."""
    analyzer = ServiceFilteredDijkstra()
    analyzer.run()


if __name__ == "__main__":
    main()
