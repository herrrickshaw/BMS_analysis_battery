#!/usr/bin/env python3
"""
Interactive Toll Plaza Dashboard with Payment Data Analysis
- Multi-month heat map visualization
- Traffic trends and collections analysis
- Interactive controls for date range and metrics
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')


class TollPlazaDashboard:
    def __init__(self, plaza_data_path, payment_data_path=None):
        """
        Initialize dashboard with toll plaza and payment data.

        Args:
            plaza_data_path: Path to cleaned toll plaza CSV
            payment_data_path: Path to payment data CSV (optional)
        """
        self.plazas = pd.read_csv(plaza_data_path)
        self.payments = None
        self.metrics = None

        if payment_data_path:
            self.load_payment_data(payment_data_path)

    def load_payment_data(self, csv_path):
        """
        Load payment data from CSV.
        Expected columns: plaza_name, date, amount, vehicle_count (optional)
        """
        self.payments = pd.read_csv(csv_path)
        self.payments['date'] = pd.to_datetime(self.payments['date'])
        self.payments['month'] = self.payments['date'].dt.strftime('%Y-%m')
        self.payments['day'] = self.payments['date'].dt.date

        print(f"✓ Loaded {len(self.payments)} payment records")
        print(f"  Date range: {self.payments['date'].min()} to {self.payments['date'].max()}")
        print(f"  Unique plazas: {self.payments['plaza_name'].nunique()}")
        print(f"  Total collections: ₹{self.payments['amount'].sum():.2f} Cr")

        self._calculate_metrics()

    def _calculate_metrics(self):
        """Calculate key metrics from payment data"""
        if self.payments is None:
            return

        self.metrics = {
            'total_collections': self.payments['amount'].sum(),
            'avg_daily_collection': self.payments.groupby('day')['amount'].sum().mean(),
            'avg_plaza_revenue': self.payments.groupby('plaza_name')['amount'].sum().mean(),
            'monthly_breakdown': self.payments.groupby('month')['amount'].sum().to_dict(),
            'state_breakdown': self._get_state_breakdown(),
            'top_plazas': self._get_top_plazas(10),
            'collection_volatility': self.payments.groupby('plaza_name')['amount'].std()
        }

    def _get_state_breakdown(self):
        """Get collections breakdown by state"""
        state_data = self.payments.merge(
            self.plazas[['plaza_name', 'state']],
            on='plaza_name',
            how='left'
        )
        return state_data.groupby('state')['amount'].sum().to_dict()

    def _get_top_plazas(self, n=10):
        """Get top N plazas by total collections"""
        return self.payments.groupby('plaza_name')['amount'].sum().nlargest(n).to_dict()

    def create_interactive_dashboard(self, output_path='toll_dashboard.html'):
        """Create interactive HTML dashboard"""
        if self.payments is None:
            print("Error: No payment data loaded. Cannot create dashboard.")
            return

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Toll Plaza Traffic & Collection Dashboard</title>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/moment.js/2.29.4/moment.min.js"></script>
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 20px;
                }}
                .container {{
                    max-width: 1400px;
                    margin: 0 auto;
                }}
                .header {{
                    background: white;
                    padding: 30px;
                    border-radius: 10px;
                    margin-bottom: 30px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                }}
                .header h1 {{
                    color: #333;
                    margin-bottom: 10px;
                    font-size: 2.5em;
                }}
                .header p {{
                    color: #666;
                    font-size: 1.1em;
                }}
                .kpi-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                .kpi-card {{
                    background: white;
                    padding: 25px;
                    border-radius: 10px;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                    text-align: center;
                    transition: transform 0.3s ease;
                }}
                .kpi-card:hover {{
                    transform: translateY(-5px);
                    box-shadow: 0 10px 25px rgba(0,0,0,0.15);
                }}
                .kpi-value {{
                    font-size: 2em;
                    font-weight: bold;
                    color: #667eea;
                    margin: 10px 0;
                }}
                .kpi-label {{
                    color: #666;
                    font-size: 0.9em;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                }}
                .charts-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                .chart-card {{
                    background: white;
                    padding: 25px;
                    border-radius: 10px;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                }}
                .chart-title {{
                    font-size: 1.2em;
                    font-weight: bold;
                    color: #333;
                    margin-bottom: 20px;
                    border-bottom: 3px solid #667eea;
                    padding-bottom: 10px;
                }}
                .table-card {{
                    background: white;
                    padding: 25px;
                    border-radius: 10px;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                    margin-bottom: 30px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 0.95em;
                }}
                th {{
                    background: #667eea;
                    color: white;
                    padding: 12px;
                    text-align: left;
                    font-weight: 600;
                }}
                td {{
                    padding: 12px;
                    border-bottom: 1px solid #eee;
                }}
                tr:hover {{
                    background: #f5f5f5;
                }}
                .footer {{
                    text-align: center;
                    color: white;
                    padding: 20px;
                    font-size: 0.9em;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚗 Toll Plaza Traffic & Collection Dashboard</h1>
                    <p>Nationwide traffic movement and revenue analysis across major toll booths</p>
                </div>

                <div class="kpi-grid">
                    <div class="kpi-card">
                        <div class="kpi-label">Total Collections</div>
                        <div class="kpi-value">₹{self.metrics['total_collections']/10000000:.2f} Cr</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-label">Average Daily</div>
                        <div class="kpi-value">₹{self.metrics['avg_daily_collection']/100000:.2f} L</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-label">Avg Plaza Revenue</div>
                        <div class="kpi-value">₹{self.metrics['avg_plaza_revenue']/100000:.2f} L</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-label">Active Plazas</div>
                        <div class="kpi-value">{self.payments['plaza_name'].nunique()}</div>
                    </div>
                </div>

                <div class="charts-grid">
                    <div class="chart-card">
                        <div class="chart-title">Monthly Collections Trend</div>
                        <canvas id="monthlyChart"></canvas>
                    </div>
                    <div class="chart-card">
                        <div class="chart-title">Top 10 Plazas by Revenue</div>
                        <canvas id="topPlazasChart"></canvas>
                    </div>
                </div>

                <div class="charts-grid">
                    <div class="chart-card">
                        <div class="chart-title">Collections by State</div>
                        <canvas id="stateChart"></canvas>
                    </div>
                </div>

                <div class="table-card">
                    <div class="chart-title">Top 15 Toll Plazas</div>
                    <table>
                        <thead>
                            <tr>
                                <th>Rank</th>
                                <th>Plaza Name</th>
                                <th>State</th>
                                <th>Total Collections (₹ Lakhs)</th>
                                <th>Revenue Share (%)</th>
                            </tr>
                        </thead>
                        <tbody id="topPlazasTable"></tbody>
                    </table>
                </div>

                <div class="footer">
                    <p>📊 Dashboard generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p>Data source: National Highway Authority of India (NHAI)</p>
                </div>
            </div>

            <script>
                // Monthly trend chart
                const monthlyData = {json.dumps(self.metrics['monthly_breakdown'])};
                const months = Object.keys(monthlyData).sort();
                const monthlyValues = months.map(m => monthlyData[m]/100000);

                new Chart(document.getElementById('monthlyChart'), {{
                    type: 'line',
                    data: {{
                        labels: months,
                        datasets: [{{
                            label: 'Collections (₹ Lakhs)',
                            data: monthlyValues,
                            borderColor: '#667eea',
                            backgroundColor: 'rgba(102, 126, 234, 0.1)',
                            borderWidth: 3,
                            fill: true,
                            tension: 0.4,
                            pointRadius: 5,
                            pointBackgroundColor: '#667eea',
                            pointHoverRadius: 7
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        plugins: {{
                            legend: {{ display: true, position: 'top' }}
                        }},
                        scales: {{
                            y: {{
                                beginAtZero: true,
                                title: {{ display: true, text: 'Collections (₹ Lakhs)' }}
                            }}
                        }}
                    }}
                }});

                // Top plazas chart
                const topPlazas = {json.dumps(self.metrics['top_plazas'])};
                const plazaNames = Object.keys(topPlazas);
                const plazaValues = Object.values(topPlazas).map(v => v/100000);

                new Chart(document.getElementById('topPlazasChart'), {{
                    type: 'bar',
                    data: {{
                        labels: plazaNames,
                        datasets: [{{
                            label: 'Collections (₹ Lakhs)',
                            data: plazaValues,
                            backgroundColor: [
                                '#667eea', '#764ba2', '#f093fb', '#4facfe', '#00f2fe',
                                '#43e97b', '#fa709a', '#fee140', '#30cfd0', '#330867'
                            ]
                        }}]
                    }},
                    options: {{
                        indexAxis: 'y',
                        responsive: true,
                        plugins: {{
                            legend: {{ display: false }}
                        }},
                        scales: {{
                            x: {{
                                beginAtZero: true,
                                title: {{ display: true, text: 'Collections (₹ Lakhs)' }}
                            }}
                        }}
                    }}
                }});

                // State breakdown chart
                const stateData = {json.dumps(self.metrics['state_breakdown'])};
                const stateNames = Object.keys(stateData).slice(0, 15);
                const stateValues = stateNames.map(s => stateData[s]/100000);

                new Chart(document.getElementById('stateChart'), {{
                    type: 'doughnut',
                    data: {{
                        labels: stateNames,
                        datasets: [{{
                            data: stateValues,
                            backgroundColor: [
                                '#667eea', '#764ba2', '#f093fb', '#4facfe', '#00f2fe',
                                '#43e97b', '#fa709a', '#fee140', '#30cfd0', '#330867',
                                '#c747d4', '#30b3f3', '#ff6b9d', '#c44569', '#ffa502'
                            ]
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        plugins: {{
                            legend: {{
                                position: 'right',
                                labels: {{ font: {{ size: 10 }} }}
                            }}
                        }}
                    }}
                }});

                // Populate top plazas table
                const tableBody = document.getElementById('topPlazasTable');
                const totalCollections = {self.metrics['total_collections']};
                let rank = 1;
                plazaNames.forEach((name, idx) => {{
                    const amount = plazaValues[idx];
                    const percentage = ((amount * 100000 / totalCollections) * 100).toFixed(2);
                    const row = `
                        <tr>
                            <td>${{rank}}</td>
                            <td>${{name}}</td>
                            <td>--</td>
                            <td>${{amount.toFixed(2)}}</td>
                            <td>${{percentage}}%</td>
                        </tr>
                    `;
                    tableBody.innerHTML += row;
                    rank++;
                }});
            </script>
        </body>
        </html>
        """

        with open(output_path, 'w') as f:
            f.write(html_content)

        print(f"✓ Interactive dashboard created: {output_path}")
        return output_path

    def export_metrics_json(self, output_path='toll_metrics.json'):
        """Export metrics as JSON for integration with other tools"""
        metrics_dict = {
            'total_collections': float(self.metrics['total_collections']),
            'avg_daily_collection': float(self.metrics['avg_daily_collection']),
            'avg_plaza_revenue': float(self.metrics['avg_plaza_revenue']),
            'monthly_breakdown': {k: float(v) for k, v in self.metrics['monthly_breakdown'].items()},
            'state_breakdown': {k: float(v) for k, v in self.metrics['state_breakdown'].items()},
            'top_plazas': {k: float(v) for k, v in self.metrics['top_plazas'].items()},
            'generated_at': datetime.now().isoformat()
        }

        with open(output_path, 'w') as f:
            json.dump(metrics_dict, f, indent=2)

        print(f"✓ Metrics exported: {output_path}")
        return output_path

    def generate_text_report(self, output_path='toll_analysis_report.txt'):
        """Generate comprehensive text report"""
        report = f"""
{'='*80}
TOLL PLAZA TRAFFIC & COLLECTION ANALYSIS REPORT
{'='*80}

EXECUTIVE SUMMARY
{'-'*80}
Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total Collections: ₹{self.metrics['total_collections']/10000000:.2f} Crore
Average Daily Collection: ₹{self.metrics['avg_daily_collection']/100000:.2f} Lakhs
Average Plaza Revenue: ₹{self.metrics['avg_plaza_revenue']/100000:.2f} Lakhs
Active Toll Plazas: {self.payments['plaza_name'].nunique()}
Date Range: {self.payments['date'].min().date()} to {self.payments['date'].max().date()}

KEY METRICS
{'-'*80}
Total Toll Plazas in Network: {len(self.plazas)}
States with Toll Infrastructure: {self.plazas['state'].nunique()}
Data Points Analyzed: {len(self.payments):,}

TOP 15 PERFORMING TOLL PLAZAS
{'-'*80}
"""
        top_15 = self.payments.groupby('plaza_name')['amount'].sum().nlargest(15)
        total_collections = self.metrics['total_collections']

        for rank, (plaza, amount) in enumerate(top_15.items(), 1):
            percentage = (amount / total_collections) * 100
            state = self.plazas[self.plazas['plaza_name'] == plaza]['state'].values[0] if len(
                self.plazas[self.plazas['plaza_name'] == plaza]) > 0 else 'Unknown'
            report += f"{rank:2d}. {str(plaza):40s} | {str(state):20s} | ₹{amount/100000:8.2f}L ({percentage:5.2f}%)\n"

        report += f"\n{'='*80}\n"
        report += "COLLECTIONS BY STATE\n"
        report += f"{'-'*80}\n"

        state_breakdown = sorted(self.metrics['state_breakdown'].items(), key=lambda x: x[1], reverse=True)
        for state, amount in state_breakdown[:15]:
            percentage = (amount / total_collections) * 100
            report += f"{state:25s}: ₹{amount/100000:10.2f}L ({percentage:5.2f}%)\n"

        report += f"\n{'='*80}\n"
        report += "MONTHLY TRENDS\n"
        report += f"{'-'*80}\n"
        report += f"{'Month':<12} | {'Collections (L)':>15} | {'Change %':>10}\n"
        report += f"{'-'*80}\n"

        months = sorted(self.metrics['monthly_breakdown'].items())
        prev_amount = None
        for month, amount in months:
            if prev_amount:
                change = ((amount - prev_amount) / prev_amount) * 100
            else:
                change = 0
            report += f"{month}  | ₹{amount/100000:13.2f} | {change:+9.2f}%\n"
            prev_amount = amount

        report += f"\n{'='*80}\n"

        with open(output_path, 'w') as f:
            f.write(report)

        print(f"✓ Text report generated: {output_path}")
        return output_path


def create_sample_payment_data(plazas_df, output_path='sample_payment_data.csv'):
    """Create sample payment data for testing"""
    records = []
    base_date = datetime(2024, 1, 1)

    valid_plazas = plazas_df.dropna(subset=['plaza_name'])

    for month in range(12):
        for day in range(1, 29):
            current_date = base_date + timedelta(days=30*month + day-1)

            for idx, row in valid_plazas.sample(n=min(100, len(valid_plazas))).iterrows():
                plaza_name = row['plaza_name']
                # Generate realistic amount
                base_amount = np.random.uniform(20, 100)  # ₹ lakhs
                daily_variation = np.random.uniform(0.7, 1.3)
                amount = base_amount * daily_variation

                records.append({
                    'plaza_name': plaza_name,
                    'date': current_date.strftime('%Y-%m-%d'),
                    'amount': amount,
                    'vehicle_count': int(np.random.uniform(500, 2000))
                })

    df = pd.DataFrame(records)
    df.to_csv(output_path, index=False)
    print(f"✓ Sample payment data created: {output_path}")
    return df


if __name__ == '__main__':
    print("Toll Plaza Dashboard Setup\n")

    # Create sample payment data
    plazas_df = pd.read_csv('/Users/umashankar/Downloads/toll_plazas_cleaned.csv')
    payment_data_path = create_sample_payment_data(plazas_df, '/Users/umashankar/Downloads/sample_payment_data.csv')

    # Initialize dashboard
    print("\nInitializing dashboard...")
    dashboard = TollPlazaDashboard(
        '/Users/umashankar/Downloads/toll_plazas_cleaned.csv',
        '/Users/umashankar/Downloads/sample_payment_data.csv'
    )

    # Generate outputs
    print("\nGenerating visualizations and reports...")
    dashboard.create_interactive_dashboard('/Users/umashankar/Downloads/toll_dashboard.html')
    dashboard.export_metrics_json('/Users/umashankar/Downloads/toll_metrics.json')
    dashboard.generate_text_report('/Users/umashankar/Downloads/toll_analysis_report.txt')

    print("\n✅ Dashboard setup complete!")
    print("\nGenerated files:")
    print("  📊 toll_dashboard.html - Interactive metrics dashboard")
    print("  📈 toll_metrics.json - Machine-readable metrics")
    print("  📄 toll_analysis_report.txt - Detailed text report")
