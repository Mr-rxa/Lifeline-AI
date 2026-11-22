let policeToken = localStorage.getItem('police_token') || '';

if(policeToken) {
    document.getElementById('policeAuth').style.display = 'none';
    document.getElementById('policeMain').style.display = 'block';
}

function togglePoliceRegistration() {
    const fields = document.getElementById('police-register-fields');
    fields.style.display = fields.style.display === 'none' ? 'block' : 'none';
}

async function registerPolice() {
    const payload = {
        username: document.getElementById('register-name').value.trim(),
        email: document.getElementById('register-email').value.trim(),
        password: document.getElementById('register-pass').value,
        role: 'police'
    };
    const err = document.getElementById('auth-err');
    if(!payload.username || !payload.email || payload.password.length < 8) {
        err.innerText = 'Name, email, and an 8-character password are required.';
        err.style.display = 'block';
        return;
    }
    const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    });
    const data = await res.json();
    if(res.ok) {
        err.style.color = 'var(--secondary-color)';
        err.innerText = 'Account created. Sign in to continue.';
    } else {
        err.style.color = 'var(--danger-color)';
        err.innerText = data.error || 'Registration failed';
    }
    err.style.display = 'block';
}

async function loginPolice() {
    const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            username: document.getElementById('auth-user').value,
            password: document.getElementById('auth-pass').value
        })
    });
    const data = await res.json();
    if(res.ok && data.user.role === 'police') {
        policeToken = data.access_token;
        localStorage.setItem('police_token', policeToken);
        document.getElementById('policeAuth').style.display = 'none';
        document.getElementById('policeMain').style.display = 'block';
        document.getElementById('police-profile').innerText = data.user.username;
    } else {
        const err = document.getElementById('auth-err');
        err.innerText = res.ok ? 'This account is not a police account.' : (data.error || 'Login failed');
        err.style.display = 'block';
    }
}

function logoutPolice() {
    localStorage.removeItem('police_token');
    window.location.reload();
}
