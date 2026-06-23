/**
 * Fuel Pump Locations Map Application
 * Interactive mapping of fuel stations across India
 */

let map, markerGroup, allMarkers = [];
let activeCompanies = new Set(COMPANIES);
let currentState = 'all';
let searchQuery = '';

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('Loading fuel pump locations map…');
    initializeMap();
    populateStateSelect();
    populateCompanyFilters();
    renderMarkers();
    updateStats();
    attachEventListeners();
    setTimeout(() => {
        document.getElementById('loader').classList.add('hidden');
        if (!document.getElementById('loader').classList.contains('hidden')) {
            document.getElementById('loader').style.display = 'none';
        }
    }, 600);
});

/**
 * Initialize Leaflet map
 */
function initializeMap() {
    map = L.map('map').setView([20.5, 78.5], 5);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '© OpenStreetMap, © CartoDB',
        maxZoom: 18,
    }).addTo(map);

    markerGroup = L.markerClusterGroup({
        chunkedLoading: true,
        iconCreateFunction: customClusterIcon,
    });
    map.addLayer(markerGroup);
}

/**
 * Custom cluster icon
 */
function customClusterIcon(cluster) {
    const count = cluster.getChildCount();
    const colors = ['#06b6d4', '#38bdf8', '#a855f7'];
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
            font-size: 13px;
            color: #0f172a;
        ">${count}</div>`,
        iconSize: [40, 40],
    });
}

/**
 * Populate state dropdown
 */
function populateStateSelect() {
    const select = document.getElementById('stateSelect');
    STATES.forEach(state => {
        const option = document.createElement('option');
        option.value = state;
        option.textContent = state;
        select.appendChild(option);
    });
}

/**
 * Populate company filters
 */
function populateCompanyFilters() {
    const container = document.getElementById('companyFilters');
    COMPANIES.forEach(company => {
        const color = COMPANY_COLORS[company];
        const label = document.createElement('label');
        label.className = 'filter-item active';
        label.style.borderColor = color;
        label.innerHTML = `
            <input type="checkbox" checked data-company="${company}">
            <span style="color: ${color}; flex: 1;">${company}</span>
            <span style="color: var(--muted); font-size: 0.7rem;">${LOCATIONS_BY_COMPANY[company].length}</span>
        `;

        const checkbox = label.querySelector('input');
        checkbox.addEventListener('change', (e) => {
            if (e.target.checked) {
                activeCompanies.add(company);
                label.classList.add('active');
            } else {
                activeCompanies.delete(company);
                label.classList.remove('active');
            }
            renderMarkers();
            updateStats();
            updateOutletList();
        });

        container.appendChild(label);
    });
}

/**
 * Render markers on map
 */
function renderMarkers() {
    markerGroup.clearLayers();
    allMarkers = [];

    let filtered = FUEL_PUMP_LOCATIONS;

    // Filter by state
    if (currentState !== 'all') {
        filtered = filtered.filter(p => p.state === currentState);
    }

    // Filter by company
    filtered = filtered.filter(p => activeCompanies.has(p.company));

    // Filter by search query
    if (searchQuery) {
        const query = searchQuery.toLowerCase();
        filtered = filtered.filter(p =>
            p.city.toLowerCase().includes(query) ||
            p.state.toLowerCase().includes(query) ||
            p.company.toLowerCase().includes(query)
        );
    }

    // Create markers
    filtered.forEach(pump => {
        const icon = createPumpIcon(pump.company);
        const marker = L.marker([pump.lat, pump.lng], { icon });

        const popup = createPumpPopup(pump);
        marker.bindPopup(popup);
        marker.pump = pump;

        markerGroup.addLayer(marker);
        allMarkers.push({ marker, pump });
    });
}

/**
 * Create marker icon based on company
 */
function createPumpIcon(company) {
    const color = COMPANY_COLORS[company];
    return L.divIcon({
        html: `<div style="
            width: 32px;
            height: 32px;
            background: ${color};
            border: 3px solid #0f172a;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 14px;
            color: #0f172a;
            box-shadow: 0 0 10px ${color};
        ">⛽</div>`,
        iconSize: [32, 32],
        className: 'pump-marker',
    });
}

/**
 * Create popup content
 */
function createPumpPopup(pump) {
    const popup = document.createElement('div');
    popup.innerHTML = `
        <div style="min-width: 200px;">
            <b style="font-size: 1.1em; color: var(--accent);">${pump.city}</b><br>
            <small style="color: var(--muted);">${pump.state}</small><br>
            <hr style="margin: 6px 0; border: none; border-top: 1px solid #334155;">
            <b style="font-size: 0.9em;">Company:</b> <span style="color: ${COMPANY_COLORS[pump.company]}">${pump.company}</span><br>
            <b style="font-size: 0.9em;">Location:</b> <small>${pump.address}</small><br>
            <hr style="margin: 6px 0; border: none; border-top: 1px solid #334155;">
            <small style="color: var(--muted);">
                <b>Coordinates:</b> ${pump.lat.toFixed(4)}, ${pump.lng.toFixed(4)}<br>
                Click to navigate
            </small>
        </div>
    `;
    return popup;
}

/**
 * Update statistics
 */
function updateStats() {
    const total = FUEL_PUMP_LOCATIONS.length;
    const showing = allMarkers.length;

    document.getElementById('statTotal').textContent = total;
    document.getElementById('statShowing').textContent = showing;
}

/**
 * Update outlet list in sidebar
 */
function updateOutletList() {
    const container = document.getElementById('outletList');
    container.innerHTML = '';

    // Group by city
    const byCityCompany = {};
    allMarkers.forEach(({ pump }) => {
        const key = `${pump.city},${pump.company}`;
        if (!byCityCompany[key]) {
            byCityCompany[key] = { city: pump.city, company: pump.company, count: 0 };
        }
        byCityCompany[key].count++;
    });

    // Sort by count
    const sorted = Object.values(byCityCompany)
        .sort((a, b) => b.count - a.count)
        .slice(0, 20);

    sorted.forEach(item => {
        const card = document.createElement('div');
        card.className = 'outlet-card';
        card.innerHTML = `
            <div class="city">${item.city}</div>
            <div class="company" style="color: ${COMPANY_COLORS[item.company]};">${item.company}</div>
            <div class="count">${item.count}</div>
        `;

        card.addEventListener('click', () => {
            // Find pump and navigate to it
            const pump = allMarkers.find(m => m.pump.city === item.city && m.pump.company === item.company)?.pump;
            if (pump) {
                map.setView([pump.lat, pump.lng], 12);
                setTimeout(() => {
                    const marker = allMarkers.find(m => m.pump === pump)?.marker;
                    if (marker) marker.openPopup();
                }, 300);
            }
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
        renderMarkers();
        updateStats();
        updateOutletList();

        if (currentState !== 'all') {
            const state = STATES.find(s => s === currentState);
            if (state) {
                const bounds = new L.LatLngBounds();
                allMarkers.forEach(({ pump }) => {
                    bounds.extend([pump.lat, pump.lng]);
                });
                if (bounds.isValid()) {
                    map.fitBounds(bounds, { padding: [50, 50] });
                }
            }
        } else {
            map.setView([20.5, 78.5], 5);
        }
    });

    document.getElementById('searchInput').addEventListener('input', (e) => {
        searchQuery = e.target.value;
        renderMarkers();
        updateStats();
        updateOutletList();
    });
}
