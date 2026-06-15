// Leaflet Map Initialization
const map = L.map('leafletMap').setView([28.6139, 77.2090], 11);
window.mapObj = map; // Global ref

L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
}).addTo(map);

const hospitalIcon = L.icon({
    iconUrl: 'https://cdn-icons-png.flaticon.com/512/508/508821.png',
    iconSize: [24, 24]
});

const ambulanceIcon = L.icon({
    iconUrl: 'https://cdn-icons-png.flaticon.com/512/1032/1032989.png',
    iconSize: [32, 32]
});

let ambulanceMarkers = {};
let incidentMarkers = {};

const incidentIcon = L.divIcon({
    html: '🚨',
    className: 'incident-icon',
    iconSize: [30, 30]
});

// Load Hospitals
async function loadMapHospitals() {
    const res = await fetch('/api/hospitals/');
    const hospitals = await res.json();
    hospitals.forEach(h => {
        L.marker([h.lat, h.lon], {icon: hospitalIcon})
         .addTo(map)
         .bindPopup(`<b>${h.name}</b><br>Beds: ${h.available_beds}`);
    });
}
loadMapHospitals();

// Server-Sent Events for Live Tracking & Notifications
let processedNotifications = new Set();

const evtSource = new EventSource("/api/tracking/stream");
evtSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    // Process GPS Positions
    const positions = data.positions || {};
    for(const ambId in positions) {
        const amb = positions[ambId];
        if(!ambulanceMarkers[ambId]) {
            ambulanceMarkers[ambId] = L.marker([amb.lat, amb.lon], {icon: ambulanceIcon})
                .addTo(map)
                .bindPopup(`<b>Ambulance ${ambId}</b><br>Speed: ${amb.speed} km/h`);
        } else {
            ambulanceMarkers[ambId].setLatLng([amb.lat, amb.lon]);
            ambulanceMarkers[ambId].setPopupContent(`<b>Ambulance ${ambId}</b><br>Speed: ${amb.speed} km/h`);
        }
    }
    
    // Process Notifications
    const notifications = data.notifications || [];
    notifications.forEach(notif => {
        if(!processedNotifications.has(notif.id)) {
            processedNotifications.add(notif.id);
            if(window.showToast) {
                window.showToast(notif.message, notif.type);
            }
        }
    });
};

// Poll Active Incidents
async function loadMapIncidents() {
    const jwt = window.token;
    if(!jwt) return;
    
    try {
        const res = await fetch('/api/incidents/', { headers: { 'Authorization': `Bearer ${jwt}`} });
        if(res.ok) {
            const incidents = await res.json();
            const activeIncidents = incidents.filter(i => i.status !== 'completed' && i.status !== 'cancelled');
            
            // Clear old
            for (let id in incidentMarkers) {
                map.removeLayer(incidentMarkers[id]);
            }
            incidentMarkers = {};
            
            activeIncidents.forEach(inc => {
                incidentMarkers[inc.id] = L.marker([inc.pickup_lat, inc.pickup_lon], {icon: incidentIcon})
                    .addTo(map)
                    .bindPopup(`<b>Incident #${inc.id}</b><br>Type: ${inc.severity}<br>Status: ${inc.status}`);
            });
        }
    } catch(e) {}
}

setInterval(() => {
    if (document.getElementById('map').classList.contains('active')) {
        loadMapIncidents();
    }
}, 3000);

// Heatmap Implementation
let heatLayer = null;
let heatmapActive = false;

window.toggleHeatmap = async function() {
    if(heatmapActive) {
        if(heatLayer) map.removeLayer(heatLayer);
        heatmapActive = false;
        if(window.showToast) window.showToast("Heatmap disabled", "info");
        return;
    }
    
    // Check if token exists from app.js
    const jwt = window.token;
    if(!jwt) return;
    
    const res = await fetch('/api/analytics/heatmap', { headers: { 'Authorization': `Bearer ${jwt}`} });
    if(res.ok) {
        const points = await res.json();
        if(heatLayer) map.removeLayer(heatLayer);
        heatLayer = L.heatLayer(points, {radius: 25, blur: 15, maxZoom: 14}).addTo(map);
        heatmapActive = true;
        if(window.showToast) window.showToast(`Heatmap enabled (${points.length} historical incidents)`, "success");
    }
};
