// Management Dashboard - Role-Aware Interface
// Handles both superadmin and location admin views

let currentUser = null;
let overviewStats = null;
let allLocations = [];
let allServers = [];
let allDevices = []; // Store all devices for editing
let managedLocationFilter = null; // For location admins to filter by specific location
let activeTab = null;

// Initialize dashboard
async function init() {
    try {
        // Load overview stats first (determines user role and permissions)
        await loadOverview();

        // Build role-appropriate tabs
        buildTabs();

        // Load initial data
        await loadInitialTabData();
    } catch (error) {
        console.error('Initialization error:', error);
        showAlert('Failed to initialize dashboard', 'error');
    }
}

// Load overview stats
async function loadOverview() {
    try {
        const response = await fetch('/api/admin/overview', {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        overviewStats = await response.json();
        currentUser = {
            is_superuser: overviewStats.is_superuser
        };

        // Update role badge
        const roleBadge = document.getElementById('roleBadge');
        if (overviewStats.is_superuser) {
            roleBadge.textContent = 'SUPERADMIN';
            roleBadge.style.background = '#dc3545';
        } else {
            roleBadge.textContent = 'LOCATION ADMIN';
            roleBadge.style.background = '#667eea';
        }

        // Show location selector for location admins
        if (!overviewStats.is_superuser && overviewStats.managed_locations.length > 1) {
            const locationContext = document.getElementById('locationContext');
            const select = document.getElementById('managedLocationSelect');

            select.innerHTML = '<option value="">All My Locations</option>';
            overviewStats.managed_locations.forEach(loc => {
                const option = document.createElement('option');
                option.value = loc.id;
                option.textContent = loc.name;
                select.appendChild(option);
            });

            locationContext.style.display = 'block';
        }

        // Build overview stats cards
        buildStatsCards();
    } catch (error) {
        console.error('Error loading overview:', error);
        throw error;
    }
}

// Build stats cards
function buildStatsCards() {
    const statsGrid = document.getElementById('statsGrid');

    const cards = [];

    // Pending devices card (always first, highlighted if > 0)
    const pendingClass = overviewStats.pending_devices > 0 ? 'stat-card pending' : 'stat-card';
    cards.push(`
        <div class="${pendingClass}" onclick="switchTab('pending')">
            <div class="stat-icon">⚠️</div>
            <div class="stat-value">${overviewStats.pending_devices}</div>
            <div class="stat-label">Pending Approvals</div>
        </div>
    `);

    // Devices card
    cards.push(`
        <div class="stat-card" onclick="switchTab('devices')">
            <div class="stat-icon">📱</div>
            <div class="stat-value">${overviewStats.total_devices}</div>
            <div class="stat-label">Devices</div>
        </div>
    `);

    // Registered faces card
    cards.push(`
        <div class="stat-card" onclick="switchTab('faces')">
            <div class="stat-icon">👥</div>
            <div class="stat-value">${overviewStats.total_registered_faces}</div>
            <div class="stat-label">Registered Faces</div>
        </div>
    `);

    // Superadmin-only cards
    if (overviewStats.is_superuser) {
        cards.push(`
            <div class="stat-card" onclick="switchTab('locations')">
                <div class="stat-icon">📍</div>
                <div class="stat-value">${overviewStats.total_locations}</div>
                <div class="stat-label">Locations</div>
            </div>
        `);

        cards.push(`
            <div class="stat-card" onclick="switchTab('users')">
                <div class="stat-icon">👤</div>
                <div class="stat-value">${overviewStats.total_users}</div>
                <div class="stat-label">Users</div>
            </div>
        `);
    } else {
        // Location admin sees their location count (but can't click - no locations tab for them)
        cards.push(`
            <div class="stat-card" style="cursor: default;">
                <div class="stat-icon">📍</div>
                <div class="stat-value">${overviewStats.total_locations}</div>
                <div class="stat-label">My Locations</div>
            </div>
        `);
    }

    statsGrid.innerHTML = cards.join('');
}

// Build tabs based on user role
function buildTabs() {
    const tabNav = document.getElementById('tabNav');
    const tabs = [];

    // Pending approvals (always first, with count badge if > 0)
    const pendingBadge = overviewStats.pending_devices > 0
        ? `<span class="badge-count">${overviewStats.pending_devices}</span>`
        : '';
    tabs.push(`
        <button class="tab-button active" onclick="switchTab('pending')">
            ⚠️ Pending${pendingBadge}
        </button>
    `);

    // Common tabs for all admins
    tabs.push(`
        <button class="tab-button" onclick="switchTab('devices')">
            📱 Devices
        </button>
    `);

    tabs.push(`
        <button class="tab-button" onclick="switchTab('faces')">
            👥 Registered Faces
        </button>
    `);

    // Superadmin-only tabs
    if (overviewStats.is_superuser) {
        tabs.push(`
            <button class="tab-button" onclick="switchTab('users')">
                👤 Users
            </button>
        `);

        tabs.push(`
            <button class="tab-button" onclick="switchTab('locations')">
                📍 Locations
            </button>
        `);

        tabs.push(`
            <button class="tab-button" onclick="switchTab('servers')">
                🖥️ Servers
            </button>
        `);
    }

    tabNav.innerHTML = tabs.join('');
}

// Switch tab
function switchTab(tabName) {
    activeTab = tabName;

    // Update tab buttons
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');

    // Update content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`${tabName}-tab`).classList.add('active');

    // Load tab data
    loadTabData(tabName);
}

// Load initial tab data
async function loadInitialTabData() {
    // Start with pending tab
    activeTab = 'pending';
    await loadTabData('pending');
}

// Load tab-specific data
async function loadTabData(tabName) {
    switch(tabName) {
        case 'pending':
            await loadPendingDevices();
            break;
        case 'devices':
            await loadDevices();
            break;
        case 'faces':
            await loadRegisteredFaces();
            break;
        case 'users':
            if (overviewStats.is_superuser) {
                await loadUsers();
            }
            break;
        case 'locations':
            if (overviewStats.is_superuser) {
                await loadLocations();
            }
            break;
        case 'servers':
            if (overviewStats.is_superuser) {
                await loadServers();
            }
            break;
    }
}

// Load pending devices
async function loadPendingDevices() {
    try {
        const response = await fetch('/api/devices/pending', {
            credentials: 'include'
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        const devices = data.devices || [];

        const container = document.getElementById('pending-devices-container');

        if (devices.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="icon">✅</div><p>No pending device approvals</p></div>';
            return;
        }

        // Load locations and servers for the approval modal
        await Promise.all([loadLocationsData(), loadServersData()]);

        container.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Registration Code</th>
                        <th>Registered At</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${devices.map(device => `
                        <tr>
                            <td><strong style="font-size: 18px; letter-spacing: 2px; font-family: monospace;">${escapeHtml(device.registration_code)}</strong></td>
                            <td>${new Date(device.registered_at).toLocaleString()}</td>
                            <td>
                                <button class="btn btn-success" onclick="showApproveDeviceModal('${device.device_id}', '${escapeHtml(device.registration_code)}')">Approve</button>
                                <button class="btn btn-danger" onclick="rejectDevice('${device.device_id}')">Reject</button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (error) {
        console.error('Error loading pending devices:', error);
        showAlert('Failed to load pending devices', 'error');
    }
}

// Load devices
async function loadDevices() {
    try {
        const response = await fetch('/api/devices?approved=true', {
            credentials: 'include'
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        allDevices = data.devices || [];

        const container = document.getElementById('devices-container');

        if (allDevices.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="icon">📱</div><p>No devices configured</p></div>';
            return;
        }

        container.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Device Name</th>
                        <th>Type</th>
                        <th>Location</th>
                        <th>Last Seen</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${allDevices.map(device => `
                        <tr>
                            <td><strong>${escapeHtml(device.device_name)}</strong></td>
                            <td><span class="badge badge-info">${escapeHtml(device.device_type)}</span></td>
                            <td>${escapeHtml(device.location_name || 'Unknown')}</td>
                            <td>${device.last_seen ? new Date(device.last_seen).toLocaleString() : 'Never'}</td>
                            <td>
                                <button class="btn btn-warning btn-sm" onclick="editDeviceById('${device.device_id}')">Edit</button>
                                <button class="btn btn-danger btn-sm" onclick="deleteDevice('${device.device_id}', '${escapeHtml(device.device_name)}')">Delete</button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (error) {
        console.error('Error loading devices:', error);
        showAlert('Failed to load devices', 'error');
    }
}

// Load registered faces
async function loadRegisteredFaces() {
    try {
        const response = await fetch('/api/registered-faces', {
            credentials: 'include'
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        const faces = data.faces || [];

        const container = document.getElementById('faces-container');

        if (faces.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="icon">👥</div><p>No registered faces</p></div>';
            return;
        }

        container.innerHTML = `
            <div class="face-grid">
                ${faces.map(face => `
                    <div class="face-card">
                        <h4>${escapeHtml(face.person_name)}</h4>
                        <p>Photos: ${face.photo_count}</p>
                        ${face.location_name ? `<p><span class="badge badge-info">${escapeHtml(face.location_name)}</span></p>` : ''}
                        <button class="btn btn-danger btn-sm" style="margin-top: 10px; width: 100%;"
                                onclick="deleteFaceFromDatabase('${escapeHtml(face.person_name)}')">Delete</button>
                    </div>
                `).join('')}
            </div>
        `;
    } catch (error) {
        console.error('Error loading registered faces:', error);
        showAlert('Failed to load registered faces', 'error');
    }
}

// Superadmin-only functions

// Load users (superadmin only)
async function loadUsers() {
    try {
        const response = await fetch('/api/admin/users', {
            credentials: 'include'
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        const users = data.users || [];

        const container = document.getElementById('users-container');

        if (users.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="icon">👤</div><p>No users found</p></div>';
            return;
        }

        container.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Email</th>
                        <th>Name</th>
                        <th>Role</th>
                        <th>Status</th>
                        <th>Locations</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${users.map(user => {
                        let statusBadge = '';
                        if (user.is_suspended) {
                            statusBadge = '<span class="badge badge-danger">Suspended</span>';
                        } else if (!user.is_active) {
                            statusBadge = '<span class="badge badge-warning">Pending</span>';
                        } else {
                            statusBadge = '<span class="badge badge-success">Active</span>';
                        }

                        const locationList = user.locations && user.locations.length > 0
                            ? user.locations.map(loc => `${escapeHtml(loc.location_name)} (${loc.role})`).join('<br>')
                            : '<span style="color: #999;">None</span>';

                        return `
                            <tr>
                                <td>${escapeHtml(user.email)}</td>
                                <td>${escapeHtml(user.first_name || '')} ${escapeHtml(user.last_name || '')}</td>
                                <td>${user.is_superuser ? '<span class="badge badge-danger">Superadmin</span>' : '<span class="badge badge-info">User</span>'}</td>
                                <td>${statusBadge}</td>
                                <td>${locationList}</td>
                                <td>
                                    ${user.id !== data.current_user_id ? `
                                        <button class="btn btn-secondary btn-sm" onclick="manageUserLocations(${user.id}, '${escapeHtml(user.email)}')">Locations</button>
                                        <button class="btn btn-danger btn-sm" onclick="deleteUser(${user.id}, '${escapeHtml(user.email)}')">Delete</button>
                                    ` : '<span style="color: #999;">Current User</span>'}
                                </td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        `;
    } catch (error) {
        console.error('Error loading users:', error);
        showAlert('Failed to load users', 'error');
    }
}

// Load locations (superadmin only)
async function loadLocations() {
    try {
        await loadLocationsData();

        const container = document.getElementById('locations-container');

        if (allLocations.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="icon">📍</div><p>No locations configured</p></div>';
            return;
        }

        container.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Address</th>
                        <th>Description</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${allLocations.map(location => `
                        <tr>
                            <td><strong>${escapeHtml(location.name)}</strong></td>
                            <td>${escapeHtml(location.address || 'N/A')}</td>
                            <td>${escapeHtml(location.description || 'N/A')}</td>
                            <td>
                                <button class="btn btn-danger btn-sm" onclick="deleteLocation(${location.id}, '${escapeHtml(location.name)}')">Delete</button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (error) {
        console.error('Error loading locations:', error);
        showAlert('Failed to load locations', 'error');
    }
}

// Load servers (superadmin only)
async function loadServers() {
    try {
        await loadServersData();

        const container = document.getElementById('servers-container');

        if (allServers.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="icon">🖥️</div><p>No servers configured</p></div>';
            return;
        }

        container.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Endpoint URL</th>
                        <th>Description</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${allServers.map(server => `
                        <tr>
                            <td><strong>${escapeHtml(server.friendly_name)}</strong></td>
                            <td><code>${escapeHtml(server.endpoint_url)}</code></td>
                            <td>${escapeHtml(server.description || 'N/A')}</td>
                            <td>
                                <button class="btn btn-danger btn-sm" onclick="deleteServer(${server.id}, '${escapeHtml(server.friendly_name)}')">Delete</button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (error) {
        console.error('Error loading servers:', error);
        showAlert('Failed to load servers', 'error');
    }
}

// Helper functions to load locations and servers data
async function loadLocationsData() {
    const response = await fetch('/api/locations', { credentials: 'include' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    allLocations = data.locations || [];
    updateLocationDropdowns();
}

async function loadServersData() {
    const response = await fetch('/api/codeproject-servers', { credentials: 'include' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    allServers = await response.json();
    updateServerDropdowns();
}

function updateLocationDropdowns() {
    const selects = [
        document.getElementById('approve-device-location'),
        document.getElementById('edit-device-location'),
        document.getElementById('assign-location-select')
    ];

    selects.forEach(select => {
        if (select) {
            const currentValue = select.value;
            select.innerHTML = '<option value="">Select a location...</option>' +
                allLocations.map(loc => `<option value="${loc.id}">${escapeHtml(loc.name)}</option>`).join('');
            if (currentValue) select.value = currentValue;
        }
    });
}

function updateServerDropdowns() {
    const selects = [
        document.getElementById('approve-device-server'),
        document.getElementById('edit-device-server')
    ];

    selects.forEach(select => {
        if (select) {
            const currentValue = select.value;
            select.innerHTML = '<option value="">Select a server...</option>' +
                allServers.map(srv => `<option value="${srv.id}">${escapeHtml(srv.friendly_name)}</option>`).join('');
            if (currentValue) select.value = currentValue;
        }
    });
}

// Device management functions

async function showApproveDeviceModal(deviceId, code) {
    document.getElementById('approve-device-id').value = deviceId;
    document.getElementById('approve-device-code').value = code;
    document.getElementById('approve-device-form').reset();
    document.getElementById('approve-device-id').value = deviceId;
    document.getElementById('approve-device-code').value = code;

    openModal('approve-device-modal');
}

document.getElementById('approve-device-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const deviceId = document.getElementById('approve-device-id').value;
    const serverId = document.getElementById('approve-device-server').value;
    const server = allServers.find(s => s.id == serverId);

    const data = {
        device_name: document.getElementById('approve-device-name').value,
        location_id: parseInt(document.getElementById('approve-device-location').value),
        device_type: document.getElementById('approve-device-type').value,
        codeproject_endpoint: server ? server.endpoint_url : ''
    };

    try {
        const response = await fetch(`/api/devices/${deviceId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showAlert('Device approved successfully', 'success');
            closeModal('approve-device-modal');
            await loadOverview(); // Refresh stats
            await loadPendingDevices();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to approve device', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error approving device', 'error');
    }
});

async function rejectDevice(deviceId) {
    if (!confirm('Are you sure you want to reject this device?')) return;

    try {
        const response = await fetch(`/api/devices/${deviceId}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        if (response.ok) {
            showAlert('Device rejected', 'success');
            await loadOverview();
            await loadPendingDevices();
        } else {
            showAlert('Failed to reject device', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error rejecting device', 'error');
    }
}

async function editDeviceById(deviceId) {
    // Find device in allDevices array
    const device = allDevices.find(d => d.device_id === deviceId);
    if (!device) {
        showAlert('Device not found', 'error');
        return;
    }

    await loadLocationsData();
    await loadServersData();

    document.getElementById('edit-device-id').value = device.device_id;
    document.getElementById('edit-device-name').value = device.device_name;
    document.getElementById('edit-device-type').value = device.device_type;
    document.getElementById('edit-device-location').value = device.location_id;

    // Find and select the server
    const server = allServers.find(s => s.endpoint_url === device.codeproject_endpoint);
    if (server) {
        document.getElementById('edit-device-server').value = server.id;
    }

    openModal('edit-device-modal');
}

document.getElementById('edit-device-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const deviceId = document.getElementById('edit-device-id').value;
    const serverId = document.getElementById('edit-device-server').value;
    const server = allServers.find(s => s.id == serverId);

    const data = {
        device_name: document.getElementById('edit-device-name').value,
        location_id: parseInt(document.getElementById('edit-device-location').value),
        device_type: document.getElementById('edit-device-type').value,
        codeproject_endpoint: server ? server.endpoint_url : ''
    };

    try {
        const response = await fetch(`/api/devices/${deviceId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showAlert('Device updated successfully', 'success');
            closeModal('edit-device-modal');
            await loadDevices();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to update device', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error updating device', 'error');
    }
});

async function deleteDevice(deviceId, deviceName) {
    if (!confirm(`Are you sure you want to delete device "${deviceName}"?`)) return;

    try {
        const response = await fetch(`/api/devices/${deviceId}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        if (response.ok) {
            showAlert('Device deleted successfully', 'success');
            await loadOverview();
            await loadDevices();
        } else {
            showAlert('Failed to delete device', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error deleting device', 'error');
    }
}

// Registered faces management
async function deleteFaceFromDatabase(personName) {
    if (!confirm(`Delete all photos for "${personName}"?`)) return;

    try {
        // This would need a backend endpoint to delete from database
        // For now, show a message
        showAlert('Face deletion requires selecting a CodeProject server', 'error');
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error deleting face', 'error');
    }
}

// User management (superadmin only)
function showCreateUserModal() {
    document.getElementById('create-user-form').reset();
    openModal('create-user-modal');
}

document.getElementById('create-user-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const data = {
        email: document.getElementById('user-email').value,
        password: document.getElementById('user-password').value,
        first_name: document.getElementById('user-first-name').value || null,
        last_name: document.getElementById('user-last-name').value || null,
        is_superuser: document.getElementById('user-is-superuser').checked
    };

    try {
        const response = await fetch('/api/admin/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showAlert('User created successfully', 'success');
            closeModal('create-user-modal');
            await loadUsers();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to create user', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error creating user', 'error');
    }
});

async function deleteUser(userId, email) {
    if (!confirm(`Delete user ${email}?`)) return;

    try {
        const response = await fetch(`/api/admin/users/${userId}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        if (response.ok) {
            showAlert('User deleted successfully', 'success');
            await loadOverview();
            await loadUsers();
        } else {
            showAlert('Failed to delete user', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error deleting user', 'error');
    }
}

// Location management (superadmin only)
function showCreateLocationModal() {
    document.getElementById('create-location-form').reset();
    openModal('create-location-modal');
}

document.getElementById('create-location-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const data = {
        name: document.getElementById('location-name').value,
        address: document.getElementById('location-address').value || null,
        description: document.getElementById('location-description').value || null,
        timezone: document.getElementById('location-timezone').value || 'UTC',
        contact_info: document.getElementById('location-contact').value || null
    };

    try {
        const response = await fetch('/api/locations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showAlert('Location created successfully', 'success');
            closeModal('create-location-modal');
            await loadOverview();
            await loadLocations();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to create location', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error creating location', 'error');
    }
});

async function deleteLocation(locationId, name) {
    if (!confirm(`Delete location "${name}"?`)) return;

    try {
        const response = await fetch(`/api/locations/${locationId}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        if (response.ok) {
            showAlert('Location deleted successfully', 'success');
            await loadOverview();
            await loadLocations();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to delete location', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error deleting location', 'error');
    }
}

// Server management (superadmin only)
function showCreateServerModal() {
    document.getElementById('create-server-form').reset();
    openModal('create-server-modal');
}

document.getElementById('create-server-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const data = {
        friendly_name: document.getElementById('server-name').value,
        endpoint_url: document.getElementById('server-url').value,
        description: document.getElementById('server-description').value || null
    };

    try {
        const response = await fetch('/api/codeproject-servers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showAlert('Server added successfully', 'success');
            closeModal('create-server-modal');
            await loadServers();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to add server', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error adding server', 'error');
    }
});

async function deleteServer(serverId, name) {
    if (!confirm(`Delete server "${name}"?`)) return;

    try {
        const response = await fetch(`/api/codeproject-servers/${serverId}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        if (response.ok) {
            showAlert('Server deleted successfully', 'success');
            await loadServers();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to delete server', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error deleting server', 'error');
    }
}

// User location management (superadmin only)
let currentManageUserId = null;

async function manageUserLocations(userId, email) {
    currentManageUserId = userId;

    document.getElementById('user-locations-modal-title').textContent = `Manage Locations for ${email}`;
    document.getElementById('user-locations-container').innerHTML = `
        <div class="loading">
            <div class="spinner"></div>
            Loading...
        </div>
    `;

    await loadLocationsData();

    openModal('manage-user-locations-modal');

    try {
        const response = await fetch(`/api/users/${userId}/locations`, {
            credentials: 'include'
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        const userLocations = data.locations || [];

        const container = document.getElementById('user-locations-container');

        if (userLocations.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>User is not assigned to any locations</p></div>';
        } else {
            container.innerHTML = `
                <h3 style="margin-bottom: 15px;">Current Location Assignments</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Location</th>
                            <th>Role</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${userLocations.map(loc => `
                            <tr>
                                <td>${escapeHtml(loc.location_name)}</td>
                                <td><span class="badge ${loc.role === 'location_admin' ? 'badge-danger' : 'badge-info'}">${escapeHtml(loc.role)}</span></td>
                                <td>
                                    <button class="btn btn-danger btn-sm"
                                            onclick="removeUserFromLocation(${userId}, ${loc.location_id}, '${escapeHtml(loc.location_name)}')">Remove</button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        }
    } catch (error) {
        console.error('Error loading user locations:', error);
        document.getElementById('user-locations-container').innerHTML = '<div class="alert alert-error">Error loading locations</div>';
    }
}

document.getElementById('assign-location-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const locationId = document.getElementById('assign-location-select').value;
    const role = document.getElementById('assign-role-select').value;

    if (!locationId) {
        showAlert('Please select a location', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/locations/${locationId}/users`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                user_id: currentManageUserId,
                role: role
            })
        });

        if (response.ok) {
            showAlert('User assigned to location successfully', 'success');
            document.getElementById('assign-location-form').reset();
            // Reload the user's locations
            const userEmail = document.getElementById('user-locations-modal-title').textContent.split(' ').pop();
            await manageUserLocations(currentManageUserId, userEmail);
            await loadUsers();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to assign user to location', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error assigning user to location', 'error');
    }
});

async function removeUserFromLocation(userId, locationId, locationName) {
    if (!confirm(`Remove user from ${locationName}?`)) return;

    try {
        const response = await fetch(`/api/locations/${locationId}/users/${userId}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        if (response.ok) {
            showAlert('User removed from location successfully', 'success');
            const userEmail = document.getElementById('user-locations-modal-title').textContent.split(' ').pop();
            await manageUserLocations(userId, userEmail);
            await loadUsers();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to remove user from location', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error removing user from location', 'error');
    }
}

// Utility functions
function changeManagementLocation() {
    const select = document.getElementById('managedLocationSelect');
    managedLocationFilter = select.value ? parseInt(select.value) : null;

    // Reload current tab with new filter
    if (activeTab) {
        loadTabData(activeTab);
    }
}

function openModal(modalId) {
    document.getElementById(modalId).classList.add('active');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
}

function showAlert(message, type = 'success') {
    const container = document.getElementById('alert-container');
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;
    container.appendChild(alert);

    setTimeout(() => {
        alert.remove();
    }, 5000);
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

async function logout() {
    try {
        await fetch('/auth/logout', { method: 'POST', credentials: 'include' });
        window.location.href = '/login';
    } catch (error) {
        window.location.href = '/login';
    }
}

// Initialize on page load
init();
