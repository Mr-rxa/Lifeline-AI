let token = localStorage.getItem('driver_token') || "";
let currentUser = null;
let currentAmbulance = null;
let currentIncident = null;
let watchId = null;
let driverMap = null;
let patientMarker = null;
let ambMarker = null;

const authScreen = document.getElementById('driverAuth');
const mainScreen = document.getElementById('driverMain');

// Initialize
if (token) {
    authScreen.style.display = 'none';
    mainScreen.style.display = 'block';
    loadDriverData();
}

async function loginDriver() {
    const user = document.getElementById('auth-user').value;
    const pass = document.getElementById('auth-pass').value;
    
    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username: user, password: pass})
        });
        const data = await res.json();
        if(res.ok) {
            token = data.access_token;
            localStorage.setItem('driver_token', token);
            authScreen.style.display = 'none';
            mainScreen.style.display = 'block';
            loadDriverData();
        } else {
            document.getElementById('auth-err').innerText = data.error || 'Login failed';
            document.getElementById('auth-err').style.display = 'block';
        }
    } catch(e) {
        document.getElementById('auth-err').innerText = 'Network error';
        document.getElementById('auth-err').style.display = 'block';
    }
}

async function loadDriverData() {
    // We need an endpoint to get the user's profile and assigned ambulance
    // Since /api/auth/login returns user info, we can also use /api/users to find ambulance
    // Actually, we can fetch all ambulances and filter by driver_id for now
    try {
        const res = await fetch('/api/ambulances/', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if(res.status === 401) {
            // token expired
            localStorage.removeItem('driver_token');
            location.reload();
            return;
        }
        const ambulances = await res.json();
        
        // We don't have a /me endpoint natively yet, but we know the JWT gives access. 
        // We'll decode JWT or just prompt for username if needed, but wait: login didn't persist username.
        // Let's just find an ambulance that is assigned to the current user's ID.
        // If we don't know the ID, we can decode the JWT.
        const payload = JSON.parse(atob(token.split('.')[1]));
        const userId = payload.sub; // assuming sub is user_id or username
        
        document.getElementById('driver-name').innerText = "User ID: " + userId;
        
        currentAmbulance = ambulances.find(a => a.driver_id == userId);
        
        if (currentAmbulance) {
            document.getElementById('amb-id').innerText = currentAmbulance.vehicle_number;
            if (currentAmbulance.current_incident_id) {
                loadIncident(currentAmbulance.current_incident_id);
            } else {
                document.getElementById('assignmentCard').style.display = 'none';
                document.getElementById('noAssignmentCard').style.display = 'block';
            }
        } else {
            document.getElementById('amb-id').innerText = "No Ambulance Assigned to You";
        }
        
    } catch(e) {
        console.error("Failed to load driver data", e);
    }
}

async function loadIncident(incId) {
    const res = await fetch('/api/incidents/', {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    const incidents = await res.json();
    currentIncident = incidents.find(i => i.id == incId);
    
    if (currentIncident) {
        document.getElementById('assignmentCard').style.display = 'block';
        document.getElementById('noAssignmentCard').style.display = 'none';
        
        document.getElementById('inc-id').innerText = '#' + currentIncident.id;
        document.getElementById('pat-name').innerText = currentIncident.patient_name || 'Unknown';
        document.getElementById('pat-phone').innerText = currentIncident.patient_phone || 'N/A';
        document.getElementById('pat-notes').innerText = currentIncident.severity + " Priority";
        document.getElementById('dest-hosp').innerText = currentIncident.target_hospital_id ? "Hospital ID: " + currentIncident.target_hospital_id : "Not Assigned";
        
        initDriverMap(currentIncident.pickup_lat, currentIncident.pickup_lon);
    }
}

function initDriverMap(lat, lon) {
    document.getElementById('driverMap').style.display = 'block';
    if (!driverMap) {
        driverMap = L.map('driverMap').setView([lat, lon], 14);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap'
        }).addTo(driverMap);
        
        patientMarker = L.marker([lat, lon]).addTo(driverMap).bindPopup("Patient Location");
    } else {
        patientMarker.setLatLng([lat, lon]);
        driverMap.setView([lat, lon]);
    }
}

async function updateIncident(status) {
    if (!currentIncident) return;
    
    const res = await fetch(`/api/incidents/${currentIncident.id}/status`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ status: status })
    });
    
    if (res.ok) {
        if(status === 'completed' || status === 'cancelled') {
            document.getElementById('assignmentCard').style.display = 'none';
            document.getElementById('noAssignmentCard').style.display = 'block';
            currentIncident = null;
        }
        // Refresh data
        loadDriverData();
    } else {
        alert("Failed to update status");
    }
}

// NOTE: We don't have an endpoint for severity override yet, we'll hit an error unless we add one or repurpose.
// We will just do a placeholder alert for now or implement if backend supports.
async function updateSeverity(severity) {
    alert("Severity overridden to " + severity + ". (Note: Requires backend PUT /incidents/id route to support severity update)");
}

// GPS Tracking
let isTracking = false;
function toggleShift() {
    const btn = document.getElementById('toggleShiftBtn');
    const status = document.getElementById('gps-status');
    
    if (isTracking) {
        if (watchId) navigator.geolocation.clearWatch(watchId);
        isTracking = false;
        btn.innerText = "Start Shift (Start GPS)";
        btn.className = "btn btn-success btn-large";
        status.innerText = "GPS Inactive";
    } else {
        if ("geolocation" in navigator) {
            watchId = navigator.geolocation.watchPosition((pos) => {
                const speed = pos.coords.speed ? (pos.coords.speed * 3.6).toFixed(1) : 0;
                status.innerText = `GPS Active: Lat ${pos.coords.latitude.toFixed(4)}, Lon ${pos.coords.longitude.toFixed(4)}, Spd ${speed} km/h`;
                
                if(currentAmbulance) {
                    fetch('/api/tracking/update', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json', 'Authorization': `Bearer ${token}`},
                        body: JSON.stringify({ 
                            ambulance_id: currentAmbulance.id, 
                            lat: pos.coords.latitude, 
                            lon: pos.coords.longitude, 
                            speed: speed 
                        })
                    }).catch(e => console.log("Failed to ping location"));
                }
                
                if (driverMap) {
                    if (!ambMarker) {
                        const ambIcon = L.divIcon({html: '🚑', className: 'amb-icon', iconSize: [30, 30]});
                        ambMarker = L.marker([pos.coords.latitude, pos.coords.longitude], {icon: ambIcon}).addTo(driverMap);
                    } else {
                        ambMarker.setLatLng([pos.coords.latitude, pos.coords.longitude]);
                    }
                    // Auto fit bounds
                    if (patientMarker) {
                        const group = new L.featureGroup([patientMarker, ambMarker]);
                        driverMap.fitBounds(group.getBounds(), {padding: [20, 20]});
                    }
                }
            }, (err) => {
                status.innerText = "GPS Error: " + err.message;
            }, { enableHighAccuracy: true });
            
            isTracking = true;
            btn.innerText = "End Shift (Stop GPS)";
            btn.className = "btn btn-danger btn-large";
        } else {
            alert("Geolocation not supported by this browser.");
        }
    }
}

// Online/Offline Detection
window.addEventListener('online', () => {
    document.getElementById('connectionStatus').className = 'online-badge';
    document.getElementById('connectionStatus').innerHTML = '<div class="status-dot"></div> Online';
});
window.addEventListener('offline', () => {
    document.getElementById('connectionStatus').className = 'offline-badge';
    document.getElementById('connectionStatus').innerHTML = '<div class="status-dot"></div> Offline';
});

// Periodic Refresh
setInterval(() => {
    if(token && navigator.onLine) {
        loadDriverData();
    }
}, 2000);
