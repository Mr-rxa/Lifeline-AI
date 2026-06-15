let currentLat = null;
let currentLon = null;
let incidentId = null;
let map = null;
let markerAmbulance = null;
let markerPatient = null;
let trackingInterval = null;

// Initialize location gathering
if (navigator.geolocation) {
    navigator.geolocation.watchPosition(
        (position) => {
            currentLat = position.coords.latitude;
            currentLon = position.coords.longitude;
            document.getElementById('location-status').innerText = "📍 Location Acquired (Ready)";
            document.getElementById('location-status').style.color = "var(--secondary-color)";
        },
        (error) => {
            console.error("Error getting location", error);
            document.getElementById('location-status').innerText = "⚠️ Failed to get precise location. Please allow GPS access.";
            document.getElementById('location-status').style.color = "var(--danger-color)";
        },
        { enableHighAccuracy: true, maximumAge: 10000, timeout: 5000 }
    );
} else {
    document.getElementById('location-status').innerText = "⚠️ Geolocation not supported by browser.";
}

async function submitEmergency() {
    if (!currentLat || !currentLon) {
        alert("Please wait for GPS location to be acquired.");
        return;
    }

    const name = document.getElementById('patient-name').value;
    const phone = document.getElementById('patient-phone').value;
    const type = document.getElementById('patient-type').value;

    const btn = document.querySelector('.sos-btn');
    btn.innerHTML = '<span style="font-size:16px;">Sending...</span>';
    btn.disabled = true;

    try {
        const res = await fetch('/api/incidents/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                patient_name: name,
                patient_phone: phone,
                description: type, // Pass Emergency Type as description
                pickup_lat: currentLat,
                pickup_lon: currentLon
            })
        });
        
        const data = await res.json();
        
        if (res.ok) {
            incidentId = data.id;
            document.getElementById('request-screen').style.display = 'none';
            document.getElementById('tracking-screen').style.display = 'block';
            document.getElementById('incident-id-display').innerText = `Incident #${incidentId}`;
            
            initMap();
            startTracking();
        } else {
            alert("Error: " + data.error);
            btn.innerHTML = 'SOS';
            btn.disabled = false;
        }
    } catch (e) {
        alert("Failed to submit emergency.");
        btn.innerHTML = 'SOS';
        btn.disabled = false;
    }
}

function initMap() {
    map = L.map('citizenMap').setView([currentLat, currentLon], 15);
    // Premium carto dark matter tiles
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap &copy; CARTO'
    }).addTo(map);

    markerPatient = L.marker([currentLat, currentLon]).addTo(map)
        .bindPopup("Your Location").openPopup();
}

function startTracking() {
    pollStatus();
    trackingInterval = setInterval(pollStatus, 2000);
}

async function pollStatus() {
    if (!incidentId) return;
    
    try {
        const res = await fetch(`/api/incidents/${incidentId}`);
        if (!res.ok) return;
        
        const inc = await res.json();
        updateTrackerUI(inc.status);
        
        // Update hospital name if assigned
        if (inc.target_hospital_id) {
            // In a real app we'd fetch hospital name, for now we just show ID or generic msg
            document.getElementById('hospital-name').innerText = "Nearest Hospital (ID: " + inc.target_hospital_id + ")";
        }

        // Fetch live positions if ambulance is assigned
        if (inc.assigned_ambulance_id) {
            fetchLivePositions(inc.assigned_ambulance_id);
        }
        
        if (inc.status === 'completed' || inc.status === 'cancelled') {
            clearInterval(trackingInterval);
            alert("This emergency incident has been closed.");
        }
    } catch (e) {
        console.error("Polling error", e);
    }
}

function updateTrackerUI(status) {
    const steps = ['pending', 'assigned', 'en_route_pickup', 'arrived_pickup'];
    
    // Reset all
    steps.forEach(s => {
        document.getElementById('step-' + s).classList.remove('active', 'completed');
    });

    let currentIndex = steps.indexOf(status);
    
    // If status is beyond these steps (e.g. en_route_hospital)
    if (currentIndex === -1 && status !== 'pending') currentIndex = 3;

    steps.forEach((s, idx) => {
        const el = document.getElementById('step-' + s);
        if (idx < currentIndex) {
            el.classList.add('completed');
            el.querySelector('.step-circle').innerHTML = '✓';
        } else if (idx === currentIndex) {
            el.classList.add('active');
        }
    });
}

// Global SSE or Poll for all live positions to get ambulance location
async function fetchLivePositions(ambId) {
    // Instead of parsing SSE manually here, let's just make a fast poll to the tracking API if we created a GET endpoint for it.
    // Wait, tracking API only exposes /stream for SSE.
    // Let's use SSE correctly.
    if (!window.trackEventSource) {
        window.trackEventSource = new EventSource('/api/tracking/stream');
        window.trackEventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            if (data.positions && data.positions[ambId]) {
                const pos = data.positions[ambId];
                updateAmbulanceMarker(pos.lat, pos.lon);
            }
        };
    }
}

const ambIcon = L.divIcon({
    html: '🚑',
    className: 'amb-icon',
    iconSize: [30, 30]
});

function updateAmbulanceMarker(lat, lon) {
    if (!markerAmbulance) {
        markerAmbulance = L.marker([lat, lon], {icon: ambIcon}).addTo(map);
    } else {
        markerAmbulance.setLatLng([lat, lon]);
    }
    
    // Auto adjust bounds
    if (markerPatient && markerAmbulance) {
        const group = new L.featureGroup([markerPatient, markerAmbulance]);
        map.fitBounds(group.getBounds(), {padding: [30, 30]});
    }
}
