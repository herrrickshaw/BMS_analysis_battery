/**
 * Petrol Station Gap Analysis — Interactive Map Application
 */

let map, markerGroup, heatLayer, allMarkers = [];
let currentState = 'all', currentDistrict = 'all';
let activeCompanies = new Set(['iocl', 'bpcl', 'hpcl', 'shell', 'nayara', 'ev']);
let heatmapMode = 'gap';
let heatmapRadius = 25;

// District mappings (simplified - major districts per state)
const DISTRICTS = {
    'Maharashtra': ['Mumbai', 'Pune', 'Nagpur', 'Aurangabad', 'Nashik', 'Kolhapur', 'Solapur', 'Amravati'],
    'Uttar Pradesh': ['Lucknow', 'Kanpur', 'Varanasi', 'Agra', 'Meerut', 'Noida', 'Ghaziabad', 'Bareilly'],
    'Karnataka': ['Bangalore', 'Mysore', 'Hubballi', 'Belgaum', 'Gulbarga', 'Mangalore', 'Udupi'],
    'Tamil Nadu': ['Chennai', 'Coimbatore', 'Madurai', 'Salem', 'Tiruppur', 'Erode', 'Kanyakumari'],
    'Telangana': ['Hyderabad', 'Warangal', 'Nalgonda', 'Adilabad', 'Medak'],
    'Andhra Pradesh': ['Vijayawada', 'Visakhapatnam', 'Tirupati', 'Guntur', 'Nellore'],
    'Gujarat': ['Ahmedabad', 'Surat', 'Vadodara', 'Rajkot', 'Jamnagar', 'Bhavnagar'],
    'Rajasthan': ['Jaipur', 'Jodhpur', 'Kota', 'Ajmer', 'Bikaner', 'Udaipur'],
    'Punjab': ['Ludhiana', 'Amritsar', 'Jalandhar', 'Patiala', 'Bathinda'],
    'West Bengal': ['Kolkata', 'Asansol', 'Durgapur', 'Darjeeling', 'Siliguri'],
    'Haryana': ['Gurgaon', 'Faridabad', 'Hisar', 'Rohtak', 'Panipat'],
    'Madhya Pradesh': ['Indore', 'Bhopal', 'Jabalpur', 'Ujjain', 'Gwalior'],
    'Odisha': ['Bhubaneswar', 'Cuttack', 'Rourkela', 'Berhampur'],
    'Bihar': ['Patna', 'Gaya', 'Bhagalpur', 'Muzaffarpur'],
    'Himachal Pradesh': ['Shimla', 'Mandi', 'Kangra', 'Solan'],
    'Uttarakhand': ['Dehradun', 'Haridwar', 'Nainital', 'Almora'],
    'Assam': ['Guwahati', 'Silchar', 'Dibrugarh', 'Nagaon'],
    'Goa': ['Panaji', 'Margao', 'Vasco da Gama'],
    'Kerala': ['Kochi', 'Thiruvananthapuram', 'Kozhikode', 'Kottayam'],
    'Chandigarh': ['Chandigarh'],
    'Delhi': ['Delhi'],
};

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    console.log('Initializing Fuel Station Gap Analysis…');
    initMap();
    populateStateSelect();
    populateCompanyChips();
    renderStations();
    updateKPIs();
    updateGapList();
    attachEventListeners();
    setTimeout(() => {
        document.getElementById('loader').classList.add('hidden');
    }, 800);
});

/**
 * Initialize Leaflet map
 */
function initMap() {
    map = L.map('map').setView([22.5, 82.5], 5); // Center on India

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '© OpenStreetMap contributors, © CartoDB',
        maxZoom: 18,
    }).addTo(map);

    markerGroup = L.markerClusterGroup({
        chunkedLoading: true,
        iconCreateFunction: customClusterIcon,
    });
    map.addLayer(markerGroup);
}

/**
 * Custom cluster icon styling
 */
function customClusterIcon(cluster) {
    const count = cluster.getChildCount();
    let size = 'large';
    if (count < 10) size = 'small';
    else if (count < 50) size = 'medium';

    const colors = ['#38bdf8', '#818cf8', '#a855f7'];
    const colorIdx = Math.min(2, Math.floor(Math.log10(count)));

    return L.divIcon({
        html: `<div style="
            width: 40px;
            height: 40px;
            background: ${colors[colorIdx]};
            border: 2px solid #0f172a;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 14px;
            color: #0f172a;
        ">${count}</div>`,
        iconSize: [40, 40],
        className: 'custom-cluster',
    });
}

/**
 * Populate state dropdown
 */
function populateStateSelect() {
    const select = document.getElementById('stateSelect');
    Object.keys(STATES).sort().forEach(state => {
        const option = document.createElement('option');
        option.value = state;
        option.textContent = state;
        select.appendChild(option);
    });
}

/**
 * Populate company filter chips
 */
function populateCompanyChips() {
    const container = document.getElementById('companyChips');
    const companies = [
        { id: 'iocl', name: 'IOCL', color: '#ef4444' },
        { id: 'bpcl', name: 'BPCL', color: '#fb923c' },
        { id: 'hpcl', name: 'HPCL', color: '#eab308' },
        { id: 'shell', name: 'Shell', color: '#3b82f6' },
        { id: 'nayara', name: 'Nayara', color: '#06b6d4' },
        { id: 'ev', name: 'EV', color: '#a855f7' },
    ];

    companies.forEach(company => {
        const chip = document.createElement('div');
        chip.className = 'chip active';
        chip.textContent = company.name;
        chip.style.borderColor = company.color;
        chip.style.color = company.color;
        chip.dataset.company = company.id;
        chip.addEventListener('click', () => toggleCompany(company.id, chip));
        container.appendChild(chip);
    });
}

/**
 * Toggle company filter
 */
function toggleCompany(companyId, chip) {
    if (activeCompanies.has(companyId)) {
        activeCompanies.delete(companyId);
        chip.classList.remove('active');
    } else {
        activeCompanies.add(companyId);
        chip.classList.add('active');
    }
    renderStations();
    updateKPIs();
    updateGapList();
}

/**
 * Render stations on map based on filters
 */
function renderStations() {
    markerGroup.clearLayers();
    allMarkers = [];

    let filteredStations = FUEL_STATIONS;

    // Filter by state
    if (currentState !== 'all') {
        filteredStations = filteredStations.filter(s => s.state === currentState);
    }

    // Filter by district
    if (currentDistrict !== 'all') {
        filteredStations = filteredStations.filter(s => s.city === currentDistrict);
    }

    // Create markers
    filteredStations.forEach(station => {
        const icon = createStationIcon(station);
        const marker = L.marker([station.lat, station.lng], { icon });

        const popup = createStationPopup(station);
        marker.bindPopup(popup);
        marker.station = station; // Attach data for heatmap

        markerGroup.addLayer(marker);
        allMarkers.push(marker);
    });

    // Update heatmap
    updateHeatmap();
}

/**
 * Create station icon
 */
function createStationIcon(station) {
    let dominantCompany = 'iocl';
    let maxCount = station.iocl;

    if (station.bpcl > maxCount) { dominantCompany = 'bpcl'; maxCount = station.bpcl; }
    if (station.hpcl > maxCount) { dominantCompany = 'hpcl'; maxCount = station.hpcl; }
    if (station.shell > maxCount) { dominantCompany = 'shell'; maxCount = station.shell; }
    if (station.nayara > maxCount) { dominantCompany = 'nayara'; maxCount = station.nayara; }

    const colors = {
        iocl: '#ef4444',
        bpcl: '#fb923c',
        hpcl: '#eab308',
        shell: '#3b82f6',
        nayara: '#06b6d4',
    };

    const gapColor = station.gap_score > 65 ? '#ef4444' : station.gap_score > 35 ? '#fb923c' : '#22d3ee';

    return L.divIcon({
        html: `<div style="
            width: 28px;
            height: 28px;
            background: ${gapColor};
            border: 3px solid #0f172a;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 12px;
            color: #0f172a;
            box-shadow: 0 0 8px ${gapColor};
        ">⛽</div>`,
        iconSize: [28, 28],
        className: 'station-marker',
    });
}

/**
 * Create popup content
 */
function createStationPopup(station) {
    const popup = document.createElement('div');
    popup.innerHTML = `
        <b>${station.city}, ${station.state}</b><br>
        <small>Population: ${(station.population / 1000000).toFixed(1)}M</small><br>
        <hr style="margin:4px 0; border:none; border-top:1px solid #334155">
        <b style="font-size:11px">Fuel Stations:</b><br>
        <small>IOCL: ${station.iocl} | BPCL: ${station.bpcl} | HPCL: ${station.hpcl}</small><br>
        <small>Shell: ${station.shell} | Nayara: ${station.nayara}</small><br>
        <small>Total: <b>${station.total_stations}</b></small><br>
        <hr style="margin:4px 0; border:none; border-top:1px solid #334155">
        <small>EV Chargers: <b>${station.ev}</b></small><br>
        <small style="color:#fb923c">Gap Score: <b>${station.gap_score.toFixed(0)}/100</b></small>
    `;
    return popup;
}

/**
 * Update heatmap based on selected mode and radius
 */
function updateHeatmap() {
    if (heatLayer) map.removeLayer(heatLayer);

    const heatPoints = [];
    const radiusMeters = heatmapRadius * 1000;

    allMarkers.forEach(marker => {
        const station = marker.station;
        let intensity = 0;

        if (heatmapMode === 'gap') {
            // Intensity = gap score (0-100 normalized to 0-1)
            intensity = station.gap_score / 100;
        } else if (heatmapMode === 'density') {
            // Intensity = station density (inverted - sparse areas glow more)
            intensity = Math.max(0, 1 - (station.density / 2));
        } else if (heatmapMode === 'ev') {
            // Intensity = EV charger density
            intensity = Math.min(1, station.ev / 200);
        }

        heatPoints.push([station.lat, station.lng, intensity]);
    });

    if (heatPoints.length > 0) {
        heatLayer = L.heatLayer(heatPoints, {
            radius: heatmapRadius,
            blur: heatmapRadius * 1.2,
            maxZoom: 16,
            minOpacity: 0.3,
            gradient: {
                0.0: '#22d3ee',  // Cyan - low need
                0.3: '#06b6d4',  // Cyan darker
                0.5: '#facc15',  // Yellow - medium need
                0.7: '#fb923c',  // Orange
                1.0: '#ef4444',  // Red - high need
            },
        });
        heatLayer.addTo(map);
    }
}

/**
 * Update KPI cards
 */
function updateKPIs() {
    let totalStations = 0, totalEV = 0, gapCount = 0, totalArea = 0;

    let filtered = FUEL_STATIONS;
    if (currentState !== 'all') {
        filtered = filtered.filter(s => s.state === currentState);
    }
    if (currentDistrict !== 'all') {
        filtered = filtered.filter(s => s.city === currentDistrict);
    }

    filtered.forEach(station => {
        totalStations += station.total_stations;
        totalEV += station.ev;
        if (station.gap_score > 50) gapCount++;
        totalArea += STATES[station.state]?.area || 0;
    });

    const avgDensity = totalArea > 0 ? (totalStations / (totalArea / 1000)).toFixed(1) : '—';

    document.getElementById('kpiTotal').textContent = totalStations;
    document.getElementById('kpiEV').textContent = totalEV;
    document.getElementById('kpiGaps').textContent = gapCount;
    document.getElementById('kpiDensity').textContent = avgDensity;
}

/**
 * Update gap zone list
 */
function updateGapList() {
    const container = document.getElementById('gapList');
    container.innerHTML = '';

    let filtered = FUEL_STATIONS;
    if (currentState !== 'all') {
        filtered = filtered.filter(s => s.state === currentState);
    }

    filtered
        .sort((a, b) => b.gap_score - a.gap_score)
        .slice(0, 15)
        .forEach(station => {
            const card = document.createElement('div');
            card.className = 'gap-card';

            let scoreClass = 'score-high';
            if (station.gap_score < 35) scoreClass = 'score-low';
            else if (station.gap_score < 65) scoreClass = 'score-med';

            card.innerHTML = `
                <div style="display:flex;justify-content:space-between;align-items:start;">
                    <div>
                        <div class="name">${station.city}</div>
                        <div class="meta">${station.state} • Pop: ${(station.population / 1000000).toFixed(1)}M</div>
                        <div class="meta">${station.total_stations} stations • ${station.density.toFixed(1)}/1000km²</div>
                    </div>
                    <div class="score ${scoreClass}">${station.gap_score.toFixed(0)}</div>
                </div>
            `;

            card.addEventListener('click', () => {
                map.setView([station.lat, station.lng], 10);
            });

            container.appendChild(card);
        });
}

/**
 * Attach event listeners
 */
function attachEventListeners() {
    document.getElementById('stateSelect').addEventListener('change', (e) => {
        currentState = e.target.value;
        currentDistrict = 'all';
        document.getElementById('districtSelect').value = 'all';
        updateDistrictSelect();
        renderStations();
        updateKPIs();
        updateGapList();
    });

    document.getElementById('districtSelect').addEventListener('change', (e) => {
        currentDistrict = e.target.value;
        renderStations();
        updateKPIs();
        updateGapList();
    });

    document.getElementById('heatLayer').addEventListener('change', (e) => {
        heatmapMode = e.target.value;
        updateHeatmap();
    });

    document.getElementById('radiusSlider').addEventListener('input', (e) => {
        heatmapRadius = parseInt(e.target.value);
        document.getElementById('radiusVal').textContent = heatmapRadius;
        updateHeatmap();
    });
}

/**
 * Update district dropdown based on selected state
 */
function updateDistrictSelect() {
    const select = document.getElementById('districtSelect');
    const districts = DISTRICTS[currentState] || [];

    select.innerHTML = '<option value="all">All Districts</option>';
    districts.forEach(district => {
        const option = document.createElement('option');
        option.value = district;
        option.textContent = district;
        select.appendChild(option);
    });
}
