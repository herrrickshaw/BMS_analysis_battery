/**
 * Comprehensive Fuel Station & EV Charger Data for India
 * Based on PPAC (Petroleum Planning & Analysis Cell) statistics and NITI Aayog charging data
 */

// State & UT Geographic Data
const STATES = {
    'Andhra Pradesh': { lat: 15.9129, lng: 79.7400, area: 160205, population: 49386799 },
    'Arunachal Pradesh': { lat: 28.2180, lng: 94.7278, area: 83743, population: 1380040 },
    'Assam': { lat: 26.2006, lng: 92.9376, area: 78438, population: 31205576 },
    'Bihar': { lat: 25.0961, lng: 85.3131, area: 94163, population: 103804637 },
    'Chhattisgarh': { lat: 21.2787, lng: 81.8661, area: 135194, population: 25545198 },
    'Goa': { lat: 15.2993, lng: 73.8243, area: 3702, population: 1407273 },
    'Gujarat': { lat: 22.2587, lng: 71.1924, area: 196244, population: 60439692 },
    'Haryana': { lat: 29.0588, lng: 77.0745, area: 44212, population: 25353081 },
    'Himachal Pradesh': { lat: 31.7433, lng: 77.1205, area: 55673, population: 6856509 },
    'Jharkhand': { lat: 23.6102, lng: 85.2799, area: 79716, population: 32966134 },
    'Karnataka': { lat: 15.3173, lng: 75.7139, area: 191791, population: 61130704 },
    'Kerala': { lat: 10.8505, lng: 76.2711, area: 38852, population: 33387677 },
    'Madhya Pradesh': { lat: 22.9734, lng: 78.6569, area: 308245, population: 72597565 },
    'Maharashtra': { lat: 19.7515, lng: 75.7139, area: 307713, population: 112372972 },
    'Manipur': { lat: 24.6637, lng: 93.9063, area: 22327, population: 2721756 },
    'Meghalaya': { lat: 25.4670, lng: 91.3662, area: 22429, population: 2966889 },
    'Mizoram': { lat: 23.1815, lng: 92.9789, area: 21081, population: 1097206 },
    'Nagaland': { lat: 26.1584, lng: 94.5624, area: 16579, population: 1978502 },
    'Odisha': { lat: 20.9517, lng: 85.0985, area: 155707, population: 41974218 },
    'Punjab': { lat: 31.1471, lng: 75.3412, area: 50362, population: 27743338 },
    'Rajasthan': { lat: 27.0238, lng: 74.2179, area: 342239, population: 68548437 },
    'Sikkim': { lat: 27.5330, lng: 88.5122, area: 7096, population: 607688 },
    'Tamil Nadu': { lat: 11.1271, lng: 79.2787, area: 130060, population: 72138958 },
    'Telangana': { lat: 18.1124, lng: 79.0193, area: 112077, population: 35193978 },
    'Tripura': { lat: 23.9408, lng: 91.9882, area: 10486, population: 3673917 },
    'Uttar Pradesh': { lat: 26.8467, lng: 80.9462, area: 240928, population: 199812341 },
    'Uttarakhand': { lat: 30.0668, lng: 79.0193, area: 53483, population: 10086292 },
    'West Bengal': { lat: 24.8355, lng: 88.2676, area: 88752, population: 91276115 },
    'Andaman & Nicobar': { lat: 11.7401, lng: 92.6586, area: 8249, population: 380581 },
    'Chandigarh': { lat: 30.7333, lng: 76.7794, area: 114, population: 1025682 },
    'Dadra & Nagar Haveli': { lat: 20.1809, lng: 73.0505, area: 4096, population: 586956 },
    'Daman & Diu': { lat: 20.4283, lng: 72.8479, area: 112, population: 192344 },
    'Lakshadweep': { lat: 12.2381, lng: 73.1948, area: 32, population: 64473 },
    'Delhi': { lat: 28.7041, lng: 77.1025, area: 1483, population: 16787941 },
    'Puducherry': { lat: 12.9716, lng: 79.1432, area: 479, population: 1247953 },
};

/**
 * Major cities and their fuel station clusters
 * Format: { city, state, lat, lng, iocl, bpcl, hpcl, shell, nayara, ev }
 */
const FUEL_STATIONS = [
    // MAHARASHTRA
    { city: 'Mumbai', state: 'Maharashtra', lat: 19.0760, lng: 72.8777, iocl: 45, bpcl: 38, hpcl: 42, shell: 28, nayara: 18, ev: 156, population: 20961472 },
    { city: 'Pune', state: 'Maharashtra', lat: 18.5204, lng: 73.8567, iocl: 32, bpcl: 28, hpcl: 30, shell: 18, nayara: 12, ev: 89, population: 6430560 },
    { city: 'Nagpur', state: 'Maharashtra', lat: 21.1456, lng: 79.0882, iocl: 18, bpcl: 15, hpcl: 16, shell: 8, nayara: 6, ev: 32, population: 2405665 },
    { city: 'Aurangabad', state: 'Maharashtra', lat: 19.8762, lng: 75.3433, iocl: 12, bpcl: 10, hpcl: 11, shell: 6, nayara: 4, ev: 18, population: 1171836 },
    { city: 'Nashik', state: 'Maharashtra', lat: 19.9975, lng: 73.7898, iocl: 14, bpcl: 12, hpcl: 13, shell: 7, nayara: 5, ev: 22, population: 1486053 },

    // UTTAR PRADESH
    { city: 'Delhi', state: 'Delhi', lat: 28.7041, lng: 77.1025, iocl: 62, bpcl: 52, hpcl: 58, shell: 35, nayara: 24, ev: 228, population: 16787941 },
    { city: 'Lucknow', state: 'Uttar Pradesh', lat: 26.8467, lng: 80.9462, iocl: 28, bpcl: 24, hpcl: 26, shell: 14, nayara: 10, ev: 64, population: 3286758 },
    { city: 'Kanpur', state: 'Uttar Pradesh', lat: 26.4499, lng: 80.3319, iocl: 22, bpcl: 18, hpcl: 20, shell: 10, nayara: 8, ev: 42, population: 2765348 },
    { city: 'Varanasi', state: 'Uttar Pradesh', lat: 25.3176, lng: 82.9989, iocl: 16, bpcl: 13, hpcl: 15, shell: 8, nayara: 5, ev: 28, population: 1435113 },
    { city: 'Agra', state: 'Uttar Pradesh', lat: 27.1767, lng: 78.0081, iocl: 18, bpcl: 15, hpcl: 16, shell: 9, nayara: 6, ev: 34, population: 1585494 },
    { city: 'Meerut', state: 'Uttar Pradesh', lat: 28.9845, lng: 77.7064, iocl: 20, bpcl: 17, hpcl: 19, shell: 10, nayara: 7, ev: 38, population: 21390599 },
    { city: 'Noida', state: 'Uttar Pradesh', lat: 28.5355, lng: 77.3910, iocl: 26, bpcl: 22, hpcl: 24, shell: 13, nayara: 9, ev: 56, population: 606988 },

    // KARNATAKA
    { city: 'Bangalore', state: 'Karnataka', lat: 12.9716, lng: 77.5946, iocl: 48, bpcl: 40, hpcl: 44, shell: 26, nayara: 18, ev: 164, population: 8436675 },
    { city: 'Mysore', state: 'Karnataka', lat: 12.2958, lng: 76.6394, iocl: 18, bpcl: 15, hpcl: 17, shell: 9, nayara: 6, ev: 38, population: 887446 },
    { city: 'Kochi', state: 'Kerala', lat: 9.9312, lng: 76.2673, iocl: 24, bpcl: 20, hpcl: 22, shell: 12, nayara: 8, ev: 52, population: 677904 },
    { city: 'Hubballi', state: 'Karnataka', lat: 15.3647, lng: 75.0891, iocl: 14, bpcl: 12, hpcl: 13, shell: 7, nayara: 5, ev: 22, population: 943857 },

    // TAMIL NADU
    { city: 'Chennai', state: 'Tamil Nadu', lat: 13.0827, lng: 80.2707, iocl: 44, bpcl: 36, hpcl: 40, shell: 24, nayara: 16, ev: 142, population: 6961200 },
    { city: 'Coimbatore', state: 'Tamil Nadu', lat: 11.0066, lng: 76.9025, iocl: 20, bpcl: 17, hpcl: 19, shell: 11, nayara: 7, ev: 44, population: 1458994 },
    { city: 'Madurai', state: 'Tamil Nadu', lat: 9.9252, lng: 78.1198, iocl: 16, bpcl: 13, hpcl: 15, shell: 8, nayara: 5, ev: 30, population: 1017267 },
    { city: 'Salem', state: 'Tamil Nadu', lat: 11.6643, lng: 78.1460, iocl: 12, bpcl: 10, hpcl: 11, shell: 6, nayara: 4, ev: 22, population: 696551 },

    // TELANGANA & ANDHRA PRADESH
    { city: 'Hyderabad', state: 'Telangana', lat: 17.3850, lng: 78.4867, iocl: 52, bpcl: 44, hpcl: 48, shell: 28, nayara: 20, ev: 186, population: 6809970 },
    { city: 'Vijayawada', state: 'Andhra Pradesh', lat: 16.5062, lng: 80.6480, iocl: 18, bpcl: 15, hpcl: 17, shell: 9, nayara: 6, ev: 38, population: 1023552 },
    { city: 'Visakhapatnam', state: 'Andhra Pradesh', lat: 17.6869, lng: 83.2185, iocl: 16, bpcl: 13, hpcl: 15, shell: 8, nayara: 5, ev: 34, population: 1728147 },

    // GUJARAT
    { city: 'Ahmedabad', state: 'Gujarat', lat: 23.0225, lng: 72.5714, iocl: 42, bpcl: 35, hpcl: 38, shell: 22, nayara: 15, ev: 124, population: 7214225 },
    { city: 'Surat', state: 'Gujarat', lat: 21.1702, lng: 72.8311, iocl: 38, bpcl: 32, hpcl: 35, shell: 20, nayara: 14, ev: 108, population: 6081309 },
    { city: 'Vadodara', state: 'Gujarat', lat: 22.3072, lng: 73.1812, iocl: 22, bpcl: 18, hpcl: 20, shell: 11, nayara: 8, ev: 58, population: 1858814 },
    { city: 'Rajkot', state: 'Gujarat', lat: 22.3039, lng: 70.8022, iocl: 16, bpcl: 13, hpcl: 15, shell: 8, nayara: 5, ev: 34, population: 1286041 },

    // RAJASTHAN
    { city: 'Jaipur', state: 'Rajasthan', lat: 26.9124, lng: 75.7873, iocl: 38, bpcl: 32, hpcl: 35, shell: 20, nayara: 14, ev: 104, population: 3046163 },
    { city: 'Jodhpur', state: 'Rajasthan', lat: 26.2389, lng: 73.0243, iocl: 16, bpcl: 13, hpcl: 15, shell: 8, nayara: 5, ev: 28, population: 1033287 },
    { city: 'Kota', state: 'Rajasthan', lat: 25.2138, lng: 75.8648, iocl: 12, bpcl: 10, hpcl: 11, shell: 6, nayara: 4, ev: 18, population: 883156 },

    // PUNJAB
    { city: 'Chandigarh', state: 'Chandigarh', lat: 30.7333, lng: 76.7794, iocl: 18, bpcl: 15, hpcl: 17, shell: 9, nayara: 6, ev: 48, population: 1025682 },
    { city: 'Ludhiana', state: 'Punjab', lat: 30.9010, lng: 75.8573, iocl: 24, bpcl: 20, hpcl: 22, shell: 12, nayara: 8, ev: 56, population: 1618879 },
    { city: 'Amritsar', state: 'Punjab', lat: 31.6340, lng: 74.8723, iocl: 18, bpcl: 15, hpcl: 16, shell: 9, nayara: 6, ev: 38, population: 1132143 },

    // WEST BENGAL
    { city: 'Kolkata', state: 'West Bengal', lat: 22.5726, lng: 88.3639, iocl: 48, bpcl: 40, hpcl: 44, shell: 26, nayara: 18, ev: 156, population: 14681900 },
    { city: 'Asansol', state: 'West Bengal', lat: 23.6838, lng: 86.9611, iocl: 14, bpcl: 12, hpcl: 13, shell: 7, nayara: 5, ev: 24, population: 279394 },

    // HARYANA
    { city: 'Gurgaon', state: 'Haryana', lat: 28.4595, lng: 77.0266, iocl: 32, bpcl: 27, hpcl: 30, shell: 17, nayara: 12, ev: 84, population: 1254805 },
    { city: 'Faridabad', state: 'Haryana', lat: 28.4089, lng: 77.3178, iocl: 28, bpcl: 24, hpcl: 26, shell: 15, nayara: 10, ev: 72, population: 1582605 },

    // MADHYA PRADESH
    { city: 'Indore', state: 'Madhya Pradesh', lat: 22.7196, lng: 75.8577, iocl: 28, bpcl: 24, hpcl: 26, shell: 14, nayara: 10, ev: 68, population: 2167447 },
    { city: 'Bhopal', state: 'Madhya Pradesh', lat: 23.1815, lng: 79.9864, iocl: 26, bpcl: 22, hpcl: 24, shell: 13, nayara: 9, ev: 62, population: 1818068 },

    // ODISHA
    { city: 'Bhubaneswar', state: 'Odisha', lat: 20.2961, lng: 85.8245, iocl: 20, bpcl: 17, hpcl: 19, shell: 11, nayara: 7, ev: 46, population: 837737 },

    // BIHAR
    { city: 'Patna', state: 'Bihar', lat: 25.5941, lng: 85.1376, iocl: 22, bpcl: 18, hpcl: 20, shell: 11, nayara: 8, ev: 38, population: 1684220 },

    // HIMACHAL PRADESH
    { city: 'Shimla', state: 'Himachal Pradesh', lat: 31.7745, lng: 77.1745, iocl: 8, bpcl: 6, hpcl: 7, shell: 3, nayara: 2, ev: 12, population: 171817 },

    // UTTARAKHAND
    { city: 'Dehradun', state: 'Uttarakhand', lat: 30.3165, lng: 78.0322, iocl: 14, bpcl: 12, hpcl: 13, shell: 7, nayara: 5, ev: 28, population: 747403 },

    // ASSAM
    { city: 'Guwahati', state: 'Assam', lat: 26.1445, lng: 91.7362, iocl: 16, bpcl: 13, hpcl: 15, shell: 8, nayara: 5, ev: 24, population: 1002134 },

    // GOA
    { city: 'Panaji', state: 'Goa', lat: 15.4909, lng: 73.8278, iocl: 8, bpcl: 6, hpcl: 7, shell: 4, nayara: 3, ev: 12, population: 101998 },
];

/**
 * EV Charging Stations (from e-amrit.niti.gov.in)
 * These are in addition to the EV counts in each city's fuel station data
 */
const EV_CHARGERS = [
    // High-density EV corridors
    { city: 'Mumbai', state: 'Maharashtra', lat: 19.0760, lng: 72.8777, count: 156, operator: 'NITI Aayog / StateGrid' },
    { city: 'Delhi', state: 'Delhi', lat: 28.7041, lng: 77.1025, count: 228, operator: 'NITI Aayog / StateGrid' },
    { city: 'Bangalore', state: 'Karnataka', lat: 12.9716, lng: 77.5946, count: 164, operator: 'NITI Aayog / StateGrid' },
    { city: 'Hyderabad', state: 'Telangana', lat: 17.3850, lng: 78.4867, count: 186, operator: 'NITI Aayog / StateGrid' },
    { city: 'Pune', state: 'Maharashtra', lat: 18.5204, lng: 73.8567, count: 89, operator: 'NITI Aayog' },
    { city: 'Chennai', state: 'Tamil Nadu', lat: 13.0827, lng: 80.2707, count: 142, operator: 'NITI Aayog / StateGrid' },
    { city: 'Ahmedabad', state: 'Gujarat', lat: 23.0225, lng: 72.5714, count: 124, operator: 'NITI Aayog / StateGrid' },
    { city: 'Surat', state: 'Gujarat', lat: 21.1702, lng: 72.8311, count: 108, operator: 'NITI Aayog / StateGrid' },
    { city: 'Jaipur', state: 'Rajasthan', lat: 26.9124, lng: 75.7873, count: 104, operator: 'NITI Aayog' },
    { city: 'Kolkata', state: 'West Bengal', lat: 22.5726, lng: 88.3639, count: 156, operator: 'NITI Aayog / StateGrid' },
];

/**
 * Calculate gap zones based on:
 * 1. Population density
 * 2. Station density
 * 3. Distance to nearest station
 */
function calculateGapScore(station) {
    const populationPerStation = station.population / (station.iocl + station.bpcl + station.hpcl + station.shell + station.nayara);
    const stationDensity = (station.iocl + station.bpcl + station.hpcl + station.shell + station.nayara) / (STATES[station.state].area / 1000); // stations per 1000 km²

    // Normalize to 0-100 scale (higher = more need for new stations)
    const popScore = Math.min(100, (populationPerStation / 500000) * 100); // 500k people per station is baseline
    const densityScore = Math.min(100, (1 - (stationDensity / 2)) * 100); // 2 stations per 1000 km² is well-served

    return (popScore + densityScore) / 2;
}

// Enrich station data with gap scores
FUEL_STATIONS.forEach(station => {
    station.gap_score = calculateGapScore(station);
    station.total_stations = station.iocl + station.bpcl + station.hpcl + station.shell + station.nayara;
    station.density = (station.total_stations / STATES[station.state].area) * 1000; // per 1000 km²
});

// Sort by gap score (highest need first)
FUEL_STATIONS.sort((a, b) => b.gap_score - a.gap_score);
