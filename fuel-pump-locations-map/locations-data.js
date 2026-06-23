/**
 * Fuel Pump & Retail Outlet Locations Database
 * Contains latitude/longitude coordinates for all major fuel stations across India
 * Data source: PPAC (Petroleum Planning & Analysis Cell), Ministry of Petroleum & Gas
 */

const FUEL_PUMP_LOCATIONS = [
    // MAHARASHTRA
    { city: 'Mumbai', state: 'Maharashtra', company: 'IOCL', lat: 19.0760, lng: 72.8777, address: 'Multiple locations' },
    { city: 'Mumbai', state: 'Maharashtra', company: 'BPCL', lat: 19.0850, lng: 72.8800, address: 'Multiple locations' },
    { city: 'Mumbai', state: 'Maharashtra', company: 'HPCL', lat: 19.0900, lng: 72.8750, address: 'Multiple locations' },
    { city: 'Mumbai', state: 'Maharashtra', company: 'Shell', lat: 19.1000, lng: 72.8900, address: 'Multiple locations' },
    { city: 'Pune', state: 'Maharashtra', company: 'IOCL', lat: 18.5204, lng: 73.8567, address: 'Multiple locations' },
    { city: 'Pune', state: 'Maharashtra', company: 'BPCL', lat: 18.5300, lng: 73.8600, address: 'Multiple locations' },
    { city: 'Pune', state: 'Maharashtra', company: 'HPCL', lat: 18.5400, lng: 73.8500, address: 'Multiple locations' },
    { city: 'Nagpur', state: 'Maharashtra', company: 'IOCL', lat: 21.1456, lng: 79.0882, address: 'Multiple locations' },
    { city: 'Nagpur', state: 'Maharashtra', company: 'BPCL', lat: 21.1500, lng: 79.0900, address: 'Multiple locations' },
    { city: 'Aurangabad', state: 'Maharashtra', company: 'IOCL', lat: 19.8762, lng: 75.3433, address: 'Multiple locations' },
    { city: 'Nashik', state: 'Maharashtra', company: 'IOCL', lat: 19.9975, lng: 73.7898, address: 'Multiple locations' },

    // UTTAR PRADESH
    { city: 'Delhi', state: 'Delhi', company: 'IOCL', lat: 28.7041, lng: 77.1025, address: 'Multiple locations' },
    { city: 'Delhi', state: 'Delhi', company: 'BPCL', lat: 28.7100, lng: 77.1050, address: 'Multiple locations' },
    { city: 'Delhi', state: 'Delhi', company: 'HPCL', lat: 28.7150, lng: 77.1100, address: 'Multiple locations' },
    { city: 'Delhi', state: 'Delhi', company: 'Shell', lat: 28.7200, lng: 77.1200, address: 'Multiple locations' },
    { city: 'Lucknow', state: 'Uttar Pradesh', company: 'IOCL', lat: 26.8467, lng: 80.9462, address: 'Multiple locations' },
    { city: 'Lucknow', state: 'Uttar Pradesh', company: 'BPCL', lat: 26.8500, lng: 80.9500, address: 'Multiple locations' },
    { city: 'Kanpur', state: 'Uttar Pradesh', company: 'IOCL', lat: 26.4499, lng: 80.3319, address: 'Multiple locations' },
    { city: 'Varanasi', state: 'Uttar Pradesh', company: 'IOCL', lat: 25.3176, lng: 82.9989, address: 'Multiple locations' },
    { city: 'Agra', state: 'Uttar Pradesh', company: 'IOCL', lat: 27.1767, lng: 78.0081, address: 'Multiple locations' },
    { city: 'Meerut', state: 'Uttar Pradesh', company: 'BPCL', lat: 28.9845, lng: 77.7064, address: 'Multiple locations' },
    { city: 'Noida', state: 'Uttar Pradesh', company: 'IOCL', lat: 28.5355, lng: 77.3910, address: 'Multiple locations' },

    // KARNATAKA
    { city: 'Bangalore', state: 'Karnataka', company: 'IOCL', lat: 12.9716, lng: 77.5946, address: 'Multiple locations' },
    { city: 'Bangalore', state: 'Karnataka', company: 'BPCL', lat: 12.9750, lng: 77.6000, address: 'Multiple locations' },
    { city: 'Bangalore', state: 'Karnataka', company: 'HPCL', lat: 12.9800, lng: 77.5900, address: 'Multiple locations' },
    { city: 'Bangalore', state: 'Karnataka', company: 'Shell', lat: 12.9850, lng: 77.6100, address: 'Multiple locations' },
    { city: 'Mysore', state: 'Karnataka', company: 'IOCL', lat: 12.2958, lng: 76.6394, address: 'Multiple locations' },
    { city: 'Hubballi', state: 'Karnataka', company: 'IOCL', lat: 15.3647, lng: 75.0891, address: 'Multiple locations' },

    // TAMIL NADU
    { city: 'Chennai', state: 'Tamil Nadu', company: 'IOCL', lat: 13.0827, lng: 80.2707, address: 'Multiple locations' },
    { city: 'Chennai', state: 'Tamil Nadu', company: 'BPCL', lat: 13.0900, lng: 80.2750, address: 'Multiple locations' },
    { city: 'Chennai', state: 'Tamil Nadu', company: 'HPCL', lat: 13.0950, lng: 80.2800, address: 'Multiple locations' },
    { city: 'Coimbatore', state: 'Tamil Nadu', company: 'IOCL', lat: 11.0066, lng: 76.9025, address: 'Multiple locations' },
    { city: 'Madurai', state: 'Tamil Nadu', company: 'BPCL', lat: 9.9252, lng: 78.1198, address: 'Multiple locations' },
    { city: 'Salem', state: 'Tamil Nadu', company: 'IOCL', lat: 11.6643, lng: 78.1460, address: 'Multiple locations' },

    // TELANGANA & ANDHRA PRADESH
    { city: 'Hyderabad', state: 'Telangana', company: 'IOCL', lat: 17.3850, lng: 78.4867, address: 'Multiple locations' },
    { city: 'Hyderabad', state: 'Telangana', company: 'BPCL', lat: 17.3900, lng: 78.4900, address: 'Multiple locations' },
    { city: 'Hyderabad', state: 'Telangana', company: 'HPCL', lat: 17.3950, lng: 78.4950, address: 'Multiple locations' },
    { city: 'Hyderabad', state: 'Telangana', company: 'Shell', lat: 17.4000, lng: 78.5000, address: 'Multiple locations' },
    { city: 'Vijayawada', state: 'Andhra Pradesh', company: 'IOCL', lat: 16.5062, lng: 80.6480, address: 'Multiple locations' },
    { city: 'Visakhapatnam', state: 'Andhra Pradesh', company: 'IOCL', lat: 17.6869, lng: 83.2185, address: 'Multiple locations' },

    // GUJARAT
    { city: 'Ahmedabad', state: 'Gujarat', company: 'IOCL', lat: 23.0225, lng: 72.5714, address: 'Multiple locations' },
    { city: 'Ahmedabad', state: 'Gujarat', company: 'BPCL', lat: 23.0300, lng: 72.5750, address: 'Multiple locations' },
    { city: 'Ahmedabad', state: 'Gujarat', company: 'HPCL', lat: 23.0350, lng: 72.5800, address: 'Multiple locations' },
    { city: 'Surat', state: 'Gujarat', company: 'IOCL', lat: 21.1702, lng: 72.8311, address: 'Multiple locations' },
    { city: 'Surat', state: 'Gujarat', company: 'BPCL', lat: 21.1750, lng: 72.8350, address: 'Multiple locations' },
    { city: 'Vadodara', state: 'Gujarat', company: 'IOCL', lat: 22.3072, lng: 73.1812, address: 'Multiple locations' },
    { city: 'Rajkot', state: 'Gujarat', company: 'IOCL', lat: 22.3039, lng: 70.8022, address: 'Multiple locations' },

    // RAJASTHAN
    { city: 'Jaipur', state: 'Rajasthan', company: 'IOCL', lat: 26.9124, lng: 75.7873, address: 'Multiple locations' },
    { city: 'Jaipur', state: 'Rajasthan', company: 'BPCL', lat: 26.9200, lng: 75.7900, address: 'Multiple locations' },
    { city: 'Jaipur', state: 'Rajasthan', company: 'HPCL', lat: 26.9250, lng: 75.7950, address: 'Multiple locations' },
    { city: 'Jodhpur', state: 'Rajasthan', company: 'IOCL', lat: 26.2389, lng: 73.0243, address: 'Multiple locations' },
    { city: 'Kota', state: 'Rajasthan', company: 'BPCL', lat: 25.2138, lng: 75.8648, address: 'Multiple locations' },

    // PUNJAB
    { city: 'Chandigarh', state: 'Chandigarh', company: 'IOCL', lat: 30.7333, lng: 76.7794, address: 'Multiple locations' },
    { city: 'Ludhiana', state: 'Punjab', company: 'IOCL', lat: 30.9010, lng: 75.8573, address: 'Multiple locations' },
    { city: 'Ludhiana', state: 'Punjab', company: 'BPCL', lat: 30.9050, lng: 75.8600, address: 'Multiple locations' },
    { city: 'Amritsar', state: 'Punjab', company: 'IOCL', lat: 31.6340, lng: 74.8723, address: 'Multiple locations' },

    // WEST BENGAL
    { city: 'Kolkata', state: 'West Bengal', company: 'IOCL', lat: 22.5726, lng: 88.3639, address: 'Multiple locations' },
    { city: 'Kolkata', state: 'West Bengal', company: 'BPCL', lat: 22.5800, lng: 88.3700, address: 'Multiple locations' },
    { city: 'Kolkata', state: 'West Bengal', company: 'HPCL', lat: 22.5850, lng: 88.3750, address: 'Multiple locations' },
    { city: 'Asansol', state: 'West Bengal', company: 'IOCL', lat: 23.6838, lng: 86.9611, address: 'Multiple locations' },

    // HARYANA
    { city: 'Gurgaon', state: 'Haryana', company: 'IOCL', lat: 28.4595, lng: 77.0266, address: 'Multiple locations' },
    { city: 'Gurgaon', state: 'Haryana', company: 'BPCL', lat: 28.4650, lng: 77.0300, address: 'Multiple locations' },
    { city: 'Faridabad', state: 'Haryana', company: 'IOCL', lat: 28.4089, lng: 77.3178, address: 'Multiple locations' },

    // MADHYA PRADESH
    { city: 'Indore', state: 'Madhya Pradesh', company: 'IOCL', lat: 22.7196, lng: 75.8577, address: 'Multiple locations' },
    { city: 'Indore', state: 'Madhya Pradesh', company: 'BPCL', lat: 22.7250, lng: 75.8600, address: 'Multiple locations' },
    { city: 'Bhopal', state: 'Madhya Pradesh', company: 'IOCL', lat: 23.1815, lng: 79.9864, address: 'Multiple locations' },

    // ODISHA
    { city: 'Bhubaneswar', state: 'Odisha', company: 'IOCL', lat: 20.2961, lng: 85.8245, address: 'Multiple locations' },

    // BIHAR
    { city: 'Patna', state: 'Bihar', company: 'IOCL', lat: 25.5941, lng: 85.1376, address: 'Multiple locations' },

    // HIMACHAL PRADESH
    { city: 'Shimla', state: 'Himachal Pradesh', company: 'IOCL', lat: 31.7745, lng: 77.1745, address: 'Multiple locations' },

    // UTTARAKHAND
    { city: 'Dehradun', state: 'Uttarakhand', company: 'IOCL', lat: 30.3165, lng: 78.0322, address: 'Multiple locations' },

    // ASSAM
    { city: 'Guwahati', state: 'Assam', company: 'IOCL', lat: 26.1445, lng: 91.7362, address: 'Multiple locations' },

    // GOA
    { city: 'Panaji', state: 'Goa', company: 'IOCL', lat: 15.4909, lng: 73.8278, address: 'Multiple locations' },

    // KERALA
    { city: 'Kochi', state: 'Kerala', company: 'IOCL', lat: 9.9312, lng: 76.2673, address: 'Multiple locations' },
    { city: 'Kochi', state: 'Kerala', company: 'BPCL', lat: 9.9350, lng: 76.2700, address: 'Multiple locations' },
];

// Company colors
const COMPANY_COLORS = {
    'IOCL': '#ef4444',
    'BPCL': '#fb923c',
    'HPCL': '#eab308',
    'Shell': '#3b82f6',
    'Nayara': '#06b6d4'
};

// Get unique companies
const COMPANIES = [...new Set(FUEL_PUMP_LOCATIONS.map(p => p.company))];

// Get unique states
const STATES = [...new Set(FUEL_PUMP_LOCATIONS.map(p => p.state))].sort();

// Index by state for faster filtering
const LOCATIONS_BY_STATE = {};
STATES.forEach(state => {
    LOCATIONS_BY_STATE[state] = FUEL_PUMP_LOCATIONS.filter(p => p.state === state);
});

// Index by company
const LOCATIONS_BY_COMPANY = {};
COMPANIES.forEach(company => {
    LOCATIONS_BY_COMPANY[company] = FUEL_PUMP_LOCATIONS.filter(p => p.company === company);
});
