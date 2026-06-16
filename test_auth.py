import requests
import secrets

BASE_URL = 'http://localhost:5000/api'
ADMIN_PASSWORD = secrets.token_urlsafe(12)
DISPATCHER_PASSWORD = secrets.token_urlsafe(12)
RESET_PASSWORD = secrets.token_urlsafe(12)
PUBLIC_PASSWORD = secrets.token_urlsafe(12)

# 1. Check Setup Status (Should be False)
res = requests.get(f'{BASE_URL}/auth/setup/status')
print("Setup Status:", res.json())
assert res.json()['setup_complete'] == False

# 2. Complete Setup
res = requests.post(f'{BASE_URL}/auth/setup/complete', json={'username': 'admin', 'email': 'admin@lifeline.ai', 'password': ADMIN_PASSWORD})
print("Setup Complete:", res.json())
assert res.status_code == 200

# 3. Check Setup Status (Should be True)
res = requests.get(f'{BASE_URL}/auth/setup/status')
print("Setup Status (After):", res.json())
assert res.json()['setup_complete'] == True

# 4. Login as Admin
res = requests.post(f'{BASE_URL}/auth/login', json={'username': 'admin', 'password': ADMIN_PASSWORD})
token = res.json().get('access_token')
print("Login:", "Success" if token else "Failed")
assert token is not None

# 5. Create a new user (via Admin Panel API)
headers = {'Authorization': f'Bearer {token}'}
res = requests.post(f'{BASE_URL}/users/', json={'username': 'dispatcher1', 'email': 'disp@lifeline.ai', 'password': DISPATCHER_PASSWORD, 'role': 'dispatcher'}, headers=headers)
print("Create User:", res.json())
assert res.status_code == 201

# 6. Verify Login works for new user
res = requests.post(f'{BASE_URL}/auth/login', json={'username': 'dispatcher1', 'password': DISPATCHER_PASSWORD})
disp_token = res.json().get('access_token')
print("Login Dispatcher:", "Success" if disp_token else "Failed")
assert disp_token is not None

# 7. Verify Protected Route Access (Dispatcher trying to access Admin Panel)
res = requests.get(f'{BASE_URL}/users/', headers={'Authorization': f'Bearer {disp_token}'})
print("Dispatcher accessing Admin:", res.status_code)
assert res.status_code == 403 # Unauthorized

# 8. Password Reset
res = requests.post(f'{BASE_URL}/auth/reset-password', json={'username': 'dispatcher1', 'new_password': RESET_PASSWORD})
print("Password Reset:", res.json())
assert res.status_code == 200

# 9. Register via public endpoint
res = requests.post(f'{BASE_URL}/auth/register', json={'username': 'publicuser', 'email': 'pub@lifeline.ai', 'password': PUBLIC_PASSWORD})
print("Public Registration:", res.json())
assert res.status_code == 201

print("ALL TESTS PASSED!")
