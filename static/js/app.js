// Theme Management
function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const target = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', target);
    localStorage.setItem('theme', target);
}

const savedTheme = localStorage.getItem('theme') || 'light';
document.documentElement.setAttribute('data-theme', savedTheme);

// Navigation
function switchTab(tabId) {
    document.querySelectorAll('.dashboard-content').forEach(el => el.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    
    document.querySelectorAll('.nav-links li').forEach(el => el.classList.remove('active'));
    event.currentTarget.classList.add('active');
    
    // Resize map if switching to it (Leaflet quirk)
    if(tabId === 'map' && window.mapObj) {
        setTimeout(() => window.mapObj.invalidateSize(), 100);
    }
}

// Global Toast System
window.showToast = function(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-msg">${message}</span>
        <span class="toast-time">${new Date().toLocaleTimeString()}</span>
    `;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = 'fadeOutRight 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 5000);
};

// Data Fetching & Charts
let token = ""; // Normally fetched via login. Assuming open for this internal dashboard or passed in.

async function fetchSummary() {
    try {
        const res = await fetch('/api/analytics/summary');
        const data = await res.json();
        
        document.getElementById('active-incidents').innerText = data.incidents.active;
        document.getElementById('critical-incidents').innerText = data.incidents.critical_active;
        document.getElementById('available-amb').innerText = data.ambulances.available;
        document.getElementById('assigned-amb').innerText = data.ambulances.assigned;
        document.getElementById('hospitals-icu').innerText = data.hospitals.with_icu;
        document.getElementById('avg-response').innerText = Math.round(data.incidents.avg_response_time_seconds / 60);
        
        updateCharts(data);
    } catch(e) {
        console.error('Error fetching summary:', e);
    }
}

let incidentChart, hospitalChart;

function updateCharts(data) {
    const ctxInc = document.getElementById('incidentChart').getContext('2d');
    const ctxHosp = document.getElementById('hospitalChart').getContext('2d');
    
    if(incidentChart) incidentChart.destroy();
    incidentChart = new Chart(ctxInc, {
        type: 'doughnut',
        data: {
            labels: ['Active', 'Completed'],
            datasets: [{
                data: [data.incidents.active, data.incidents.completed],
                backgroundColor: ['#e74c3c', '#2ecc71']
            }]
        },
        options: { responsive: true, maintainAspectRatio: false }
    });
    
    if(hospitalChart) hospitalChart.destroy();
    hospitalChart = new Chart(ctxHosp, {
        type: 'bar',
        data: {
            labels: ['Available Beds', 'Occupied'],
            datasets: [{
                label: 'Beds',
                data: [data.hospitals.available_beds, data.hospitals.total_beds - data.hospitals.available_beds],
                backgroundColor: ['#3498db', '#95a5a6']
            }]
        },
        options: { responsive: true, maintainAspectRatio: false }
    });
}

// Fetch Incidents
let allIncidents = [];
async function fetchIncidents() {
    const res = await fetch('/api/incidents/', { headers: { 'Authorization': `Bearer ${token}`} });
    if(res.ok) {
        allIncidents = await res.json();
        const tbody = document.getElementById('incidents-list');
        tbody.innerHTML = '';
        allIncidents.forEach(inc => {
            let actionsHtml = '';
            if (inc.status === 'pending' || inc.status === 'assigned') {
                actionsHtml = `<button class="btn btn-primary" onclick="openAssignmentModal(${inc.id}, '${inc.severity}')">Manage Assignment</button>`;
            } else {
                actionsHtml = `
                    <select onchange="updateIncidentStatus(${inc.id}, this.value)" style="padding:5px; border-radius:5px; background:var(--bg-color); color:var(--text-color); border:1px solid var(--border-color);">
                        <option value="">Status: ${inc.status}</option>
                        <option value="en_route_pickup">En Route Pickup</option>
                        <option value="arrived_pickup">Arrived Pickup</option>
                        <option value="en_route_hospital">En Route Hospital</option>
                        <option value="arrived_hospital">Arrived Hospital</option>
                        <option value="completed">Completed</option>
                        <option value="cancelled">Cancelled</option>
                    </select>
                `;
            }

            tbody.innerHTML += `
                <tr>
                    <td><a href="#" onclick="showTimeline(${inc.id}); return false;" style="color:var(--primary-color); font-weight:bold;">#${inc.id}</a></td>
                    <td>${inc.patient_name || 'Unknown'}</td>
                    <td>${inc.patient_phone || 'N/A'}</td>
                    <td><span class="badge ${inc.severity}">${inc.severity}</span></td>
                    <td><span class="badge ${inc.status}">${inc.status.replace(/_/g, ' ')}</span></td>
                    <td>${inc.assigned_ambulance_id ? '#' + inc.assigned_ambulance_id : 'Unassigned'}</td>
                    <td>${inc.target_hospital_id ? '#' + inc.target_hospital_id : 'N/A'}</td>
                    <td>${actionsHtml}</td>
                </tr>
            `;
        });
    }
}

function showTimeline(id) {
    const inc = allIncidents.find(i => i.id === id);
    if(!inc) return;
    
    document.getElementById('incidentTimelineModal').style.display = 'block';
    const container = document.getElementById('timeline-content');
    container.innerHTML = '';
    
    const steps = [
        { name: "Emergency Logged", time: inc.created_at },
        { name: "Ambulance Dispatched", time: inc.dispatched_at },
        { name: "En Route to Pickup", time: inc.en_route_pickup_at },
        { name: "Arrived at Pickup", time: inc.arrived_pickup_at },
        { name: "En Route to Hospital", time: inc.en_route_hospital_at },
        { name: "Arrived at Hospital", time: inc.arrived_hospital_at },
        { name: "Completed", time: inc.completed_at }
    ];
    
    let lastTime = null;
    steps.forEach(step => {
        if(step.time) {
            const tDate = new Date(step.time);
            let deltaText = "";
            if(lastTime) {
                const diffSecs = Math.round((tDate - lastTime) / 1000);
                deltaText = `(+${diffSecs}s)`;
            }
            container.innerHTML += `
                <div class="timeline-item">
                    <div class="timeline-title">${step.name}</div>
                    <div class="timeline-time">${tDate.toLocaleTimeString()}</div>
                    ${deltaText ? `<div class="timeline-delta">${deltaText}</div>` : ''}
                </div>
            `;
            lastTime = tDate;
        }
    });
    
    if(container.innerHTML === '') {
        container.innerHTML = '<p>No timeline data available yet.</p>';
    }
}

function showNewIncidentModal() {
    document.getElementById('newIncidentModal').style.display = 'block';
    document.getElementById('inc-name').value = '';
    document.getElementById('inc-phone').value = '';
    document.getElementById('inc-desc').value = '';
    document.getElementById('inc-lat').value = '';
    document.getElementById('inc-lon').value = '';
}

async function submitIncident() {
    const data = {
        patient_name: document.getElementById('inc-name').value,
        patient_phone: document.getElementById('inc-phone').value,
        description: document.getElementById('inc-desc').value,
        pickup_lat: parseFloat(document.getElementById('inc-lat').value),
        pickup_lon: parseFloat(document.getElementById('inc-lon').value)
    };
    
    if(!data.pickup_lat || !data.pickup_lon) {
        alert("Latitude and Longitude are required.");
        return;
    }
    
    const res = await fetch('/api/incidents/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(data)
    });
    
    if(res.ok) {
        const resData = await res.json();
        document.getElementById('newIncidentModal').style.display = 'none';
        if(resData.ai_reasoning) {
            window.showToast("Smart Dispatch: " + resData.ai_reasoning, "success");
        }
        fetchIncidents();
        fetchSummary();
    } else {
        const err = await res.json();
        alert(err.error || 'Failed to dispatch incident');
    }
}

async function updateIncidentStatus(id, status) {
    if(!status) return;
    const res = await fetch(`/api/incidents/${id}/status`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ status: status })
    });
    if(res.ok) {
        fetchIncidents();
        fetchSummary();
    }
}

async function openAssignmentModal(incId, type) {
    document.getElementById('assign-inc-id').innerText = incId;
    document.getElementById('assign-inc-type').innerText = type;
    document.getElementById('assign-target-incident-id').value = incId;
    
    // Fetch ambulances
    const res = await fetch('/api/ambulances/', { headers: { 'Authorization': `Bearer ${token}` } });
    if (res.ok) {
        const ambulances = await res.json();
        const tbody = document.getElementById('assign-amb-list');
        tbody.innerHTML = '';
        
        // Show available and currently assigned to this incident
        const validAmbs = ambulances.filter(a => a.status === 'available' || a.current_incident_id === incId);
        
        validAmbs.forEach(amb => {
            const isAssigned = amb.current_incident_id === incId;
            let actionBtn = '';
            if (isAssigned) {
                actionBtn = `<button class="btn btn-danger" onclick="unassignAmbulance(${incId})">Unassign</button>`;
            } else {
                actionBtn = `<button class="btn btn-primary" onclick="assignAmbulance(${incId}, ${amb.id})">Assign</button>`;
            }
            
            tbody.innerHTML += `
                <tr style="${isAssigned ? 'background:rgba(59,130,246,0.1);' : ''}">
                    <td>${amb.vehicle_number} (${amb.type})</td>
                    <td>${amb.status}</td>
                    <td>Calculating...</td>
                    <td>${actionBtn}</td>
                </tr>
            `;
        });
        
        if (validAmbs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4">No available ambulances right now.</td></tr>';
        }
        
        document.getElementById('assignmentModal').style.display = 'block';
    }
}

async function assignAmbulance(incId, ambId) {
    const res = await fetch(`/api/incidents/${incId}/assign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ ambulance_id: ambId })
    });
    if (res.ok) {
        document.getElementById('assignmentModal').style.display = 'none';
        fetchIncidents();
        fetchFleet();
        fetchSummary();
        window.showToast("Ambulance Assigned successfully", "success");
    } else {
        const data = await res.json();
        alert(data.error || "Assignment failed");
    }
}

async function unassignAmbulance(incId) {
    const res = await fetch(`/api/incidents/${incId}/unassign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }
    });
    if (res.ok) {
        document.getElementById('assignmentModal').style.display = 'none';
        fetchIncidents();
        fetchFleet();
        fetchSummary();
        window.showToast("Ambulance Unassigned", "info");
    }
}

// Fetch Hospitals
async function fetchHospitals() {
    const res = await fetch('/api/hospitals/');
    if(res.ok) {
        const data = await res.json();
        const tbody = document.getElementById('hospitals-list');
        tbody.innerHTML = '';
        data.forEach(h => {
            const bedPct = h.total_beds > 0 ? ((h.total_beds - h.available_beds) / h.total_beds) * 100 : 0;
            const icuPct = h.total_icu_beds > 0 ? ((h.total_icu_beds - h.available_icu_beds) / h.total_icu_beds) * 100 : 0;
            
            tbody.innerHTML += `
                <tr>
                    <td><b>${h.name}</b></td>
                    <td style="min-width:150px;">
                        ${h.available_beds} / ${h.total_beds}
                        <div class="progress-bg"><div class="progress-bar ${bedPct > 80 ? 'high' : ''}" style="width:${bedPct}%"></div></div>
                    </td>
                    <td style="min-width:150px;">
                        ${h.available_icu_beds} / ${h.total_icu_beds}
                        <div class="progress-bg"><div class="progress-bar ${icuPct > 80 ? 'high' : ''}" style="width:${icuPct}%"></div></div>
                    </td>
                    <td>${h.ventilators_available}</td>
                    <td><button class="btn btn-secondary" onclick="openEditHospital(${h.id}, ${h.available_beds}, ${h.available_icu_beds}, ${h.ventilators_available})">Manage Capacity</button></td>
                </tr>
            `;
        });
    }
}

function openEditHospital(id, beds, icu, vents) {
    document.getElementById('editHospitalModal').style.display = 'block';
    document.getElementById('edit-hosp-id').value = id;
    document.getElementById('edit-hosp-beds').value = beds;
    document.getElementById('edit-hosp-icu').value = icu;
    document.getElementById('edit-hosp-vents').value = vents;
}

async function submitHospitalUpdate() {
    const id = document.getElementById('edit-hosp-id').value;
    const res = await fetch(`/api/hospitals/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({
            available_beds: document.getElementById('edit-hosp-beds').value,
            available_icu_beds: document.getElementById('edit-hosp-icu').value,
            ventilators_available: document.getElementById('edit-hosp-vents').value
        })
    });
    
    if(res.ok) {
        document.getElementById('editHospitalModal').style.display = 'none';
        fetchHospitals();
        fetchSummary();
    }
}

// Fleet Management
async function fetchFleet() {
    const res = await fetch('/api/ambulances/', { headers: { 'Authorization': `Bearer ${token}` } });
    if(res.ok) {
        const data = await res.json();
        const tbody = document.getElementById('fleet-list');
        tbody.innerHTML = '';
        data.forEach(amb => {
            tbody.innerHTML += `
                <tr>
                    <td>#${amb.id}</td>
                    <td>${amb.vehicle_number}</td>
                    <td>${amb.type}</td>
                    <td><span class="badge ${amb.status}">${amb.status}</span></td>
                    <td>${amb.driver_id || 'Unassigned'}</td>
                    <td>${amb.current_incident_id ? '#' + amb.current_incident_id : 'None'}</td>
                </tr>
            `;
        });
    }
}

function showNewAmbulanceModal() {
    const vnum = prompt("Enter Vehicle Number (e.g. AMB-101):");
    if(vnum) {
        submitAmbulance(vnum);
    }
}

async function submitAmbulance(vehicle_number) {
    const res = await fetch('/api/ambulances/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ vehicle_number: vehicle_number, type: 'ALS' })
    });
    if(res.ok) {
        fetchFleet();
        fetchSummary();
    } else {
        alert("Failed to add ambulance. Vehicle number must be unique.");
    }
}

// --- AUTH & ONBOARDING SYSTEM ---
const authContainer = document.getElementById('authContainer');
const authTitle = document.getElementById('authTitle');
const authInputs = document.getElementById('authInputs');
const authSubmitBtn = document.getElementById('authSubmitBtn');
const authError = document.getElementById('authError');
const authLinks = document.getElementById('authLinks');
let currentAuthMode = 'login'; // login, register, setup, forgot

async function checkSetupStatus() {
    try {
        const res = await fetch('/api/auth/setup/status');
        const data = await res.json();
        if(!data.setup_complete) {
            renderAuthScreen('setup');
        } else {
            renderAuthScreen('login');
        }
    } catch(e) {
        console.error("Failed to check setup status");
        renderAuthScreen('login'); // fallback
    }
}

function renderAuthScreen(mode) {
    authContainer.style.display = 'flex';
    document.getElementById('app-container').style.display = 'none';
    authError.style.display = 'none';
    currentAuthMode = mode;
    
    if(mode === 'setup') {
        authTitle.innerText = "Welcome to LifeLine AI\nFirst-Run Setup";
        authInputs.innerHTML = `
            <input type="text" id="auth-user" placeholder="Admin Username" class="auth-input">
            <input type="email" id="auth-email" placeholder="Admin Email" class="auth-input">
            <input type="password" id="auth-pass" placeholder="Admin Password" class="auth-input">
        `;
        authSubmitBtn.innerText = "Complete Setup";
        authSubmitBtn.onclick = performSetup;
        authLinks.innerHTML = "";
    } else if(mode === 'login') {
        authTitle.innerText = "Login";
        authInputs.innerHTML = `
            <input type="text" id="auth-user" placeholder="Username" class="auth-input">
            <input type="password" id="auth-pass" placeholder="Password" class="auth-input">
        `;
        authSubmitBtn.innerText = "Login";
        authSubmitBtn.onclick = performLogin;
        authLinks.innerHTML = `
            <span onclick="renderAuthScreen('register')">Create Account</span> | 
            <span onclick="renderAuthScreen('forgot')">Forgot Password</span>
        `;
    } else if(mode === 'register') {
        authTitle.innerText = "Register Account";
        authInputs.innerHTML = `
            <input type="text" id="auth-user" placeholder="Username" class="auth-input">
            <input type="email" id="auth-email" placeholder="Email" class="auth-input">
            <input type="password" id="auth-pass" placeholder="Password" class="auth-input">
        `;
        authSubmitBtn.innerText = "Register";
        authSubmitBtn.onclick = performRegister;
        authLinks.innerHTML = `<span onclick="renderAuthScreen('login')">Back to Login</span>`;
    } else if(mode === 'forgot') {
        authTitle.innerText = "Reset Password";
        authInputs.innerHTML = `<input type="email" id="auth-email" placeholder="Registered Email" class="auth-input">`;
        authSubmitBtn.innerText = "Send Reset Link";
        authSubmitBtn.onclick = performForgotPassword;
        authLinks.innerHTML = `<span onclick="renderAuthScreen('login')">Back to Login</span>`;
    }
}

async function performSetup() {
    const user = document.getElementById('auth-user').value;
    const email = document.getElementById('auth-email').value;
    const pass = document.getElementById('auth-pass').value;
    
    const res = await fetch('/api/auth/setup/complete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username: user, email: email, password: pass})
    });
    
    if(res.ok) {
        alert("Setup complete! Please login with your new admin credentials.");
        renderAuthScreen('login');
    } else {
        const data = await res.json();
        authError.innerText = data.error || 'Setup failed';
        authError.style.display = 'block';
    }
}

async function performRegister() {
    const user = document.getElementById('auth-user').value;
    const email = document.getElementById('auth-email').value;
    const pass = document.getElementById('auth-pass').value;
    
    const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username: user, email: email, password: pass})
    });
    
    if(res.ok) {
        alert("Registration successful! You can now log in.");
        renderAuthScreen('login');
    } else {
        const data = await res.json();
        authError.innerText = data.error || 'Registration failed';
        authError.style.display = 'block';
    }
}

async function performForgotPassword() {
    const email = document.getElementById('auth-email').value;
    const res = await fetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({email: email})
    });
    const data = await res.json();
    alert(data.message);
    renderAuthScreen('login');
}

async function performLogin() {
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
            authContainer.style.display = 'none';
            document.getElementById('app-container').style.display = 'flex';
            
            document.getElementById('currentUser').innerText = data.user.username;
            if(data.user.role === 'admin') {
                document.getElementById('nav-admin').style.display = 'flex';
            }
            
            initializeApp();
        } else {
            authError.innerText = data.error || 'Login failed';
            authError.style.display = 'block';
        }
    } catch(e) {
        authError.innerText = 'Network error';
        authError.style.display = 'block';
    }
}

async function performLogout() {
    try {
        await fetch('/api/auth/logout', {
            method: 'POST',
            headers: {'Authorization': `Bearer ${token}`}
        });
    } catch(e) {}
    token = "";
    document.getElementById('nav-admin').style.display = 'none';
    checkSetupStatus();
}

function showProfileSettings() {
    document.getElementById('profileModal').style.display = 'flex';
    document.getElementById('profileError').style.display = 'none';
    document.getElementById('profileSuccess').style.display = 'none';
    document.getElementById('profile-new-pass').value = '';
}

async function changePassword() {
    const newPass = document.getElementById('profile-new-pass').value;
    const username = document.getElementById('currentUser').innerText;
    
    if(!newPass) return;
    
    const res = await fetch('/api/auth/reset-password', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'Authorization': `Bearer ${token}`},
        body: JSON.stringify({username: username, new_password: newPass})
    });
    
    if(res.ok) {
        document.getElementById('profileSuccess').innerText = "Password updated successfully.";
        document.getElementById('profileSuccess').style.display = 'block';
        setTimeout(() => document.getElementById('profileModal').style.display = 'none', 1500);
    } else {
        document.getElementById('profileError').innerText = "Failed to update password.";
        document.getElementById('profileError').style.display = 'block';
    }
}

// User Management (Admin Panel)
async function fetchUsers() {
    const res = await fetch('/api/users/', { headers: { 'Authorization': `Bearer ${token}`} });
    if(res.ok) {
        const data = await res.json();
        const tbody = document.getElementById('users-list');
        tbody.innerHTML = '';
        data.forEach(u => {
            tbody.innerHTML += `
                <tr>
                    <td>${u.id}</td>
                    <td>${u.username}</td>
                    <td>${u.email}</td>
                    <td>
                        <select onchange="updateUserRole(${u.id}, this.value)">
                            <option value="admin" ${u.role==='admin'?'selected':''}>Admin</option>
                            <option value="dispatcher" ${u.role==='dispatcher'?'selected':''}>Dispatcher</option>
                            <option value="driver" ${u.role==='driver'?'selected':''}>Driver</option>
                        </select>
                    </td>
                    <td>
                        <select onchange="updateUserStatus(${u.id}, this.value)">
                            <option value="active" ${u.status==='active'?'selected':''}>Active</option>
                            <option value="suspended" ${u.status==='suspended'?'selected':''}>Suspended</option>
                        </select>
                    </td>
                    <td>${u.last_login ? new Date(u.last_login).toLocaleString() : 'Never'}</td>
                    <td><button class="btn btn-danger" style="padding:5px;" onclick="deleteUser(${u.id})">Delete</button></td>
                </tr>
            `;
        });
    }
}

async function updateUserRole(id, role) {
    await fetch(`/api/users/${id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json', 'Authorization': `Bearer ${token}`},
        body: JSON.stringify({role: role})
    });
}

async function updateUserStatus(id, status) {
    await fetch(`/api/users/${id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json', 'Authorization': `Bearer ${token}`},
        body: JSON.stringify({status: status})
    });
}

async function deleteUser(id) {
    if(!confirm("Are you sure you want to delete this user?")) return;
    const res = await fetch(`/api/users/${id}`, {
        method: 'DELETE',
        headers: {'Authorization': `Bearer ${token}`}
    });
    if(res.ok) {
        fetchUsers();
    } else {
        const data = await res.json();
        alert(data.error);
    }
}

function initializeApp() {
    // Aggressive polling for real-time command center feel
    setInterval(() => {
        fetchSummary();
        fetchIncidents();
        fetchFleet();
        fetchHospitals();
    }, 2000);
    
    fetchSummary();
    fetchHospitals();
    fetchIncidents();
    fetchFleet();
    if(document.getElementById('nav-admin').style.display !== 'none') {
        fetchUsers();
    }
}

// Start sequence
checkSetupStatus(); 
