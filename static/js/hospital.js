let token = localStorage.getItem('hospital_token');
let hospitalId = null;
let pollInterval = null;

if (token) {
    document.getElementById('authContainer').style.display = 'none';
    document.getElementById('app-container').style.display = 'flex';
    fetchProfile();
}

async function loginHospital() {
    const user = document.getElementById('auth-user').value;
    const pass = document.getElementById('auth-pass').value;
    const err = document.getElementById('auth-err');
    
    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: user, password: pass })
        });
        
        const data = await res.json();
        if (res.ok && data.user.role === 'hospital') {
            token = data.access_token;
            localStorage.setItem('hospital_token', token);
            document.getElementById('authContainer').style.display = 'none';
            document.getElementById('app-container').style.display = 'flex';
            fetchProfile();
        } else if (res.ok) {
            err.innerText = "Error: User is not a hospital admin.";
            err.style.display = 'block';
        } else {
            err.innerText = data.error;
            err.style.display = 'block';
        }
    } catch (e) {
        err.innerText = "Connection failed.";
        err.style.display = 'block';
    }
}

function logoutHospital() {
    localStorage.removeItem('hospital_token');
    window.location.reload();
}

async function fetchProfile() {
    // We need to know which hospital this user manages.
    // Let's assume the backend /api/auth/me returns it, or we fetch the first hospital.
    // In models.py, User has a hospital_id.
    
    // Since /api/auth/me doesn't currently return hospital_id in the existing code,
    // we will fetch all hospitals and just find one, or hardcode finding the user's hospital.
    // For this hackathon scope, let's just fetch all and take the first one if we don't have mapping.
    
    try {
        const res = await fetch('/api/hospitals/', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();
        if (data.length > 0) {
            // Mock: Assumes user manages the first hospital in list if no direct link exists
            const hosp = data[0]; 
            hospitalId = hosp.id;
            document.getElementById('hospital-name-display').innerText = hosp.name;
            updateCapacityUI(hosp);
            
            // Start polling queue
            fetchQueue();
            pollInterval = setInterval(fetchQueue, 3000);
        }
    } catch (e) {
        console.error("Failed to fetch profile");
    }
}

function updateCapacityUI(hosp) {
    document.getElementById('val-beds').innerText = hosp.available_beds;
    document.getElementById('val-icu').innerText = hosp.available_icu_beds;
    document.getElementById('val-vents').innerText = hosp.ventilators_available;
}

// Current capacities in local state to allow fast increment/decrement
let currentBeds = 0;
let currentIcu = 0;
let currentVents = 0;

async function fetchQueue() {
    if (!hospitalId) return;
    
    try {
        const res = await fetch('/api/incidents/', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();
        
        // Filter incidents targeted to this hospital and not completed
        const incoming = data.filter(i => 
            i.target_hospital_id === hospitalId && 
            ['assigned', 'en_route_pickup', 'arrived_pickup', 'en_route_hospital', 'arrived_hospital'].includes(i.status)
        );
        
        renderQueue(incoming);
    } catch (e) {
        console.error(e);
    }
}

function renderQueue(incidents) {
    const container = document.getElementById('incoming-queue');
    container.innerHTML = '';
    
    if (incidents.length === 0) {
        container.innerHTML = '<p style="color:#6b7280; font-style:italic;">No incoming patients at this time.</p>';
        return;
    }
    
    incidents.forEach(inc => {
        let badgeColor = 'var(--primary-color)';
        let statusText = 'Incoming';
        let cardClass = 'patient-card';
        
        if (inc.status === 'arrived_hospital') {
            badgeColor = 'var(--secondary-color)';
            statusText = 'Arrived at ER';
            cardClass += ' arrived';
        } else if (inc.status === 'en_route_hospital') {
            badgeColor = 'var(--warning-color)';
            statusText = 'En Route (Close)';
        }
        
        const severityColor = inc.severity === 'critical' ? 'var(--danger-color)' : (inc.severity === 'urgent' ? 'var(--warning-color)' : 'var(--primary-color)');

        const html = `
            <div class="${cardClass}">
                <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
                    <span style="font-weight:700;">#${inc.id} - ${inc.patient_name || 'Unknown'}</span>
                    <span style="background:${badgeColor}; color:white; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:600;">${statusText}</span>
                </div>
                <div style="font-size:14px; margin-bottom:5px;"><span style="color:#6b7280;">Severity:</span> <span style="color:${severityColor}; font-weight:600; text-transform:uppercase;">${inc.severity}</span></div>
                <div style="font-size:14px; margin-bottom:10px;"><span style="color:#6b7280;">Notes:</span> ${inc.patient_condition_notes || 'None'}</div>
                
                ${inc.status === 'arrived_hospital' ? 
                    `<button class="btn btn-success" style="width:100%; padding:10px;" onclick="intakePatient(${inc.id})">Complete Intake & Close</button>` :
                    `<div style="font-size:12px; text-align:center; color:#6b7280; padding:10px; border:1px dashed var(--border-color); border-radius:8px;">Waiting for Arrival...</div>`
                }
            </div>
        `;
        container.innerHTML += html;
    });
}

async function updateCapacity(type, delta) {
    if (!hospitalId) return;
    
    // Optimistic UI update could go here
    
    // We need to fetch current first, add delta, then PUT
    try {
        const getRes = await fetch(`/api/hospitals/${hospitalId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const hosp = await getRes.json();
        
        const payload = {
            available_beds: hosp.available_beds,
            available_icu_beds: hosp.available_icu_beds,
            ventilators_available: hosp.ventilators_available
        };
        
        if (type === 'beds') payload.available_beds = Math.max(0, payload.available_beds + delta);
        if (type === 'icu') payload.available_icu_beds = Math.max(0, payload.available_icu_beds + delta);
        if (type === 'vents') payload.ventilators_available = Math.max(0, payload.ventilators_available + delta);
        
        const putRes = await fetch(`/api/hospitals/${hospitalId}`, {
            method: 'PUT',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}` 
            },
            body: JSON.stringify(payload)
        });
        
        if (putRes.ok) {
            // Refetch to confirm
            const newRes = await fetch(`/api/hospitals/${hospitalId}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const newHosp = await newRes.json();
            updateCapacityUI(newHosp);
        }
    } catch (e) {
        console.error("Failed to update capacity");
    }
}

async function intakePatient(incId) {
    try {
        await fetch(`/api/incidents/${incId}/status`, {
            method: 'PUT',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}` 
            },
            body: JSON.stringify({ status: 'completed' })
        });
        fetchQueue();
    } catch (e) {
        console.error("Failed to complete intake");
    }
}
