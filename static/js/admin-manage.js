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
        // Check if location_id is in URL parameters
        const urlParams = new URLSearchParams(window.location.search);
        const locationIdParam = urlParams.get('location_id');
        if (locationIdParam) {
            managedLocationFilter = parseInt(locationIdParam);
        }

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
        // Build URL with location filter if set
        let url = '/api/admin/overview';
        if (managedLocationFilter) {
            url += `?location_id=${managedLocationFilter}`;
        }

        const response = await fetch(url, {
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

        // Populate location filter dropdown
        const select = document.getElementById('managedLocationSelect');
        const locationContext = document.getElementById('locationContext');
        const currentSelection = managedLocationFilter; // Preserve current selection

        if (overviewStats.is_superuser) {
            // Superadmin: Show "All Locations" + all locations
            select.innerHTML = '<option value="">All Locations</option>';
            overviewStats.managed_locations.forEach(loc => {
                const option = document.createElement('option');
                option.value = loc.id;
                option.textContent = loc.name;
                select.appendChild(option);
            });
        } else {
            // Location admin: Show their locations
            if (overviewStats.managed_locations.length > 1) {
                select.innerHTML = '<option value="">All My Locations</option>';
            } else {
                select.innerHTML = '<option value="">Select Location...</option>';
            }
            overviewStats.managed_locations.forEach(loc => {
                const option = document.createElement('option');
                option.value = loc.id;
                option.textContent = loc.name;
                select.appendChild(option);
            });
        }

        // Restore the selected value
        if (currentSelection) {
            select.value = currentSelection;
        }

        locationContext.style.display = 'block';

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

    // Remember current active tab, or default to 'pending'
    const currentActive = activeTab || 'pending';

    // Pending approvals (always first, with count badge if > 0)
    const pendingBadge = overviewStats.pending_devices > 0
        ? `<span class="badge-count">${overviewStats.pending_devices}</span>`
        : '';
    const pendingActive = currentActive === 'pending' ? 'active' : '';
    tabs.push(`
        <button class="tab-button ${pendingActive}" onclick="switchTab('pending')">
            ⚠️ Pending${pendingBadge}
        </button>
    `);

    // Common tabs for all admins
    const devicesActive = currentActive === 'devices' ? 'active' : '';
    tabs.push(`
        <button class="tab-button ${devicesActive}" onclick="switchTab('devices')">
            📱 Devices
        </button>
    `);

    const facesActive = currentActive === 'faces' ? 'active' : '';
    tabs.push(`
        <button class="tab-button ${facesActive}" onclick="switchTab('faces')">
            👥 Registered Faces
        </button>
    `);

    // Superadmin-only tabs
    if (overviewStats.is_superuser) {
        const usersActive = currentActive === 'users' ? 'active' : '';
        tabs.push(`
            <button class="tab-button ${usersActive}" onclick="switchTab('users')">
                👤 Users
            </button>
        `);

        const locationsActive = currentActive === 'locations' ? 'active' : '';
        tabs.push(`
            <button class="tab-button ${locationsActive}" onclick="switchTab('locations')">
                📍 Locations
            </button>
        `);

        const serversActive = currentActive === 'servers' ? 'active' : '';
        tabs.push(`
            <button class="tab-button ${serversActive}" onclick="switchTab('servers')">
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
        // Refresh overview stats first to get latest counts
        await loadOverview();
        buildStatsCards();
        buildTabs();

        // Note: Pending devices are NOT filtered by location since they
        // haven't been assigned to a location yet (assigned during approval)
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
        // Build URL with location filter
        let url = '/api/devices?approved=true';
        if (managedLocationFilter) {
            url += `&location_id=${managedLocationFilter}`;
        }

        const response = await fetch(url, {
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
                        <th>Token Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${allDevices.map(device => {
                        const tokenStatus = device.token_status || 'missing';
                        const tokenAge = device.token_age_days !== null && device.token_age_days !== undefined ? `${device.token_age_days}d` : '';
                        const tokenBadgeClass = tokenStatus === 'active' ? 'badge-success' : 'badge-secondary';
                        const tokenDisplay = tokenStatus === 'active' ? `Active ${tokenAge ? `(${tokenAge})` : ''}` : 'No Token';

                        return `
                        <tr>
                            <td><strong>${escapeHtml(device.device_name)}</strong></td>
                            <td><span class="badge badge-info">${escapeHtml(device.device_type)}</span></td>
                            <td>${escapeHtml(device.location_name || 'Unknown')}</td>
                            <td>${device.last_seen ? new Date(device.last_seen).toLocaleString() : 'Never'}</td>
                            <td><span class="badge ${tokenBadgeClass}">${tokenDisplay}</span></td>
                            <td>
                                <button class="btn btn-warning btn-sm" onclick="editDeviceById('${device.device_id}')">Edit</button>
                                ${tokenStatus === 'active' ? `<button class="btn btn-secondary btn-sm" onclick="revokeDeviceToken('${device.device_id}', '${escapeHtml(device.device_name)}')">Revoke Token</button>` : ''}
                                <button class="btn btn-danger btn-sm" onclick="deleteDevice('${device.device_id}', '${escapeHtml(device.device_name)}')">Delete</button>
                            </td>
                        </tr>
                        `;
                    }).join('')}
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
        // Build URL with location filter
        let url = '/api/registered-faces';
        if (managedLocationFilter) {
            url += `?location_id=${managedLocationFilter}`;
        }

        const response = await fetch(url, {
            credentials: 'include'
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        const faces = data.faces || [];

        const container = document.getElementById('faces-container');

        if (faces.length === 0) {
            // Check if it's because no location is selected
            if (data.message && data.message.includes('select a location')) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="icon">📍</div>
                        <p>${data.message}</p>
                        <p style="margin-top: 10px; color: #999;">Please select a location from the main dashboard first.</p>
                    </div>
                `;
            } else {
                container.innerHTML = '<div class="empty-state"><div class="icon">👥</div><p>No registered faces</p></div>';
            }
            return;
        }

        container.innerHTML = `
            <div class="face-grid">
                ${faces.map(face => `
                    <div class="face-card">
                        ${face.photo ? `
                            <div style="width: 100%; height: 150px; overflow: hidden; border-radius: 8px; margin-bottom: 10px; background: #f0f0f0; display: flex; align-items: center; justify-content: center;">
                                <img src="${escapeHtml(face.photo)}"
                                     alt="${escapeHtml(face.person_name)}"
                                     style="width: 100%; height: 100%; object-fit: cover; object-position: center 25%;"
                                     onerror="this.style.display='none'; this.parentElement.innerHTML='<div style=\\'padding: 20px; color: #999;\\'>📷</div>';">
                            </div>
                        ` : `
                            <div style="width: 100%; height: 150px; border-radius: 8px; margin-bottom: 10px; background: #f0f0f0; display: flex; align-items: center; justify-content: center; font-size: 48px;">
                                👤
                            </div>
                        `}
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
        // Build URL with location filter
        let url = '/api/admin/users';
        if (managedLocationFilter) {
            url += `?location_id=${managedLocationFilter}`;
        }

        const response = await fetch(url, {
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
            <div style="margin-bottom: 15px; padding: 10px; background: #f8f9fa; border-radius: 8px; display: flex; gap: 20px; align-items: center;">
                <strong>Location Access Legend:</strong>
                <span class="badge badge-danger">Admin</span>
                <span class="badge badge-info">User</span>
            </div>
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
                            ? user.locations.map(loc => {
                                const badgeClass = loc.role === 'location_admin' ? 'badge-danger' : 'badge-info';
                                return `<span class="badge ${badgeClass}" style="margin: 2px;">${escapeHtml(loc.location_name)}</span>`;
                            }).join(' ')
                            : '<span style="color: #999;">None</span>';

                        // Build action buttons
                        let actionButtons = '';
                        if (user.id !== data.current_user_id) {
                            // Show Approve button for pending users
                            if (!user.is_active && !user.is_suspended) {
                                actionButtons += `<button class="btn btn-success btn-sm" onclick="approveUser(${user.id}, '${escapeHtml(user.email)}')">Approve</button> `;
                            }
                            actionButtons += `<button class="btn btn-secondary btn-sm" onclick="manageUserLocations(${user.id}, '${escapeHtml(user.email)}')">Locations</button> `;
                            actionButtons += `<button class="btn btn-danger btn-sm" onclick="deleteUser(${user.id}, '${escapeHtml(user.email)}')">Delete</button>`;
                        } else {
                            actionButtons = '<span style="color: #999;">Current User</span>';
                        }

                        return `
                            <tr>
                                <td>${escapeHtml(user.email)}</td>
                                <td>${escapeHtml(user.first_name || '')} ${escapeHtml(user.last_name || '')}</td>
                                <td>${user.is_superuser ? '<span class="badge badge-danger">Superadmin</span>' : '<span class="badge badge-info">User</span>'}</td>
                                <td>${statusBadge}</td>
                                <td>${locationList}</td>
                                <td>${actionButtons}</td>
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

// Handle device type change to show/hide CodeProject server selection and scanner settings
document.getElementById('approve-device-type').addEventListener('change', (e) => {
    const serverGroup = document.getElementById('approve-device-server-group');
    const serverSelect = document.getElementById('approve-device-server');
    const processingMode = document.getElementById('approve-device-processing-mode');
    const scannerSettings = document.getElementById('approve-device-scanner-settings');
    const dashboardSettings = document.getElementById('approve-device-dashboard-settings');

    if (e.target.value === 'location_dashboard') {
        serverGroup.style.display = 'none';
        serverSelect.removeAttribute('required');
        processingMode.style.display = 'none';
        scannerSettings.style.display = 'none';
        dashboardSettings.style.display = 'block';
    } else {
        serverGroup.style.display = 'block';
        serverSelect.setAttribute('required', 'required');
        dashboardSettings.style.display = 'none';

        // Show processing mode for devices that process images (kiosk and scanner)
        if (e.target.value === 'registration_kiosk' || e.target.value === 'people_scanner') {
            processingMode.style.display = 'block';
        } else {
            processingMode.style.display = 'none';
        }

        // Show scanner settings only for people_scanner
        if (e.target.value === 'people_scanner') {
            scannerSettings.style.display = 'block';
        } else {
            scannerSettings.style.display = 'none';
        }
    }
});

document.getElementById('approve-device-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const deviceId = document.getElementById('approve-device-id').value;
    const deviceType = document.getElementById('approve-device-type').value;
    const serverId = document.getElementById('approve-device-server').value;
    const server = allServers.find(s => s.id == serverId);

    const data = {
        device_name: document.getElementById('approve-device-name').value,
        location_id: parseInt(document.getElementById('approve-device-location').value),
        device_type: deviceType,
        codeproject_endpoint: deviceType === 'location_dashboard' ? null : (server ? server.endpoint_url : '')
    };

    // Add processing mode for devices that process images
    if (deviceType === 'registration_kiosk' || deviceType === 'people_scanner') {
        const processingModeRadio = document.querySelector('input[name="approve-processing-mode"]:checked');
        data.processing_mode = processingModeRadio ? processingModeRadio.value : 'server';
    }

    // Add scanner settings if device is a people_scanner
    if (deviceType === 'people_scanner') {
        const confidence = document.getElementById('approve-device-confidence').value;
        const presence = document.getElementById('approve-device-presence').value;
        const cooldown = document.getElementById('approve-device-cooldown').value;

        if (confidence) data.confidence_threshold = parseFloat(confidence);
        if (presence) data.presence_timeout_minutes = parseInt(presence);
        if (cooldown) data.detection_cooldown_seconds = parseInt(cooldown);
    }

    // Add dashboard settings if device is a location_dashboard
    if (deviceType === 'location_dashboard') {
        const dashboardTimeout = document.getElementById('approve-device-dashboard-timeout').value;
        if (dashboardTimeout) data.dashboard_display_timeout_minutes = parseInt(dashboardTimeout);
    }

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
            buildTabs(); // Update pending badge in tab
            buildStatsCards(); // Update stats cards
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
            buildTabs(); // Update pending badge in tab
            buildStatsCards(); // Update stats cards
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

    // Show/hide server dropdown and processing mode based on device type
    const serverGroup = document.getElementById('edit-device-server-group');
    const serverSelect = document.getElementById('edit-device-server');
    const processingMode = document.getElementById('edit-device-processing-mode');
    const scannerSettings = document.getElementById('edit-device-scanner-settings');

    if (device.device_type === 'location_dashboard') {
        serverGroup.style.display = 'none';
        serverSelect.removeAttribute('required');
        processingMode.style.display = 'none';
        scannerSettings.style.display = 'none';
    } else {
        serverGroup.style.display = 'block';
        serverSelect.setAttribute('required', 'required');

        // Show processing mode for devices that process images
        if (device.device_type === 'registration_kiosk' || device.device_type === 'people_scanner') {
            processingMode.style.display = 'block';
            // Set processing mode radio button
            const processingModeValue = device.processing_mode || 'server';
            const radioButton = document.querySelector(`input[name="edit-processing-mode"][value="${processingModeValue}"]`);
            if (radioButton) {
                radioButton.checked = true;
            }
        } else {
            processingMode.style.display = 'none';
        }

        // Show scanner settings only for people_scanner
        if (device.device_type === 'people_scanner') {
            scannerSettings.style.display = 'block';
            // Populate scanner settings
            document.getElementById('edit-device-confidence').value = device.confidence_threshold || '';
            document.getElementById('edit-device-presence').value = device.presence_timeout_minutes || '';
            document.getElementById('edit-device-cooldown').value = device.detection_cooldown_seconds || '';
        } else {
            scannerSettings.style.display = 'none';
        }
    }

    openModal('edit-device-modal');
}

// Handle edit device type change to show/hide CodeProject server selection and scanner settings
document.getElementById('edit-device-type').addEventListener('change', (e) => {
    const serverGroup = document.getElementById('edit-device-server-group');
    const serverSelect = document.getElementById('edit-device-server');
    const processingMode = document.getElementById('edit-device-processing-mode');
    const scannerSettings = document.getElementById('edit-device-scanner-settings');
    const dashboardSettings = document.getElementById('edit-device-dashboard-settings');

    if (e.target.value === 'location_dashboard') {
        serverGroup.style.display = 'none';
        serverSelect.removeAttribute('required');
        processingMode.style.display = 'none';
        scannerSettings.style.display = 'none';
        dashboardSettings.style.display = 'block';
    } else {
        serverGroup.style.display = 'block';
        serverSelect.setAttribute('required', 'required');
        dashboardSettings.style.display = 'none';

        // Show processing mode for devices that process images (kiosk and scanner)
        if (e.target.value === 'registration_kiosk' || e.target.value === 'people_scanner') {
            processingMode.style.display = 'block';
        } else {
            processingMode.style.display = 'none';
        }

        // Show scanner settings only for people_scanner
        if (e.target.value === 'people_scanner') {
            scannerSettings.style.display = 'block';
        } else {
            scannerSettings.style.display = 'none';
        }
    }
});

document.getElementById('edit-device-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const deviceId = document.getElementById('edit-device-id').value;
    const deviceType = document.getElementById('edit-device-type').value;
    const serverId = document.getElementById('edit-device-server').value;
    const server = allServers.find(s => s.id == serverId);

    const data = {
        device_name: document.getElementById('edit-device-name').value,
        location_id: parseInt(document.getElementById('edit-device-location').value),
        device_type: deviceType,
        codeproject_endpoint: deviceType === 'location_dashboard' ? null : (server ? server.endpoint_url : '')
    };

    // Add processing mode for devices that process images
    if (deviceType === 'registration_kiosk' || deviceType === 'people_scanner') {
        const processingModeRadio = document.querySelector('input[name="edit-processing-mode"]:checked');
        data.processing_mode = processingModeRadio ? processingModeRadio.value : 'server';
    }

    // Add scanner settings if device is a people_scanner
    if (deviceType === 'people_scanner') {
        const confidence = document.getElementById('edit-device-confidence').value;
        const presence = document.getElementById('edit-device-presence').value;
        const cooldown = document.getElementById('edit-device-cooldown').value;

        if (confidence) data.confidence_threshold = parseFloat(confidence);
        if (presence) data.presence_timeout_minutes = parseInt(presence);
        if (cooldown) data.detection_cooldown_seconds = parseInt(cooldown);
    }

    // Add dashboard settings if device is a location_dashboard
    if (deviceType === 'location_dashboard') {
        const dashboardTimeout = document.getElementById('edit-device-dashboard-timeout').value;
        if (dashboardTimeout) data.dashboard_display_timeout_minutes = parseInt(dashboardTimeout);
    }

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

async function revokeDeviceToken(deviceId, deviceName) {
    if (!confirm(`Revoke authentication token for device "${deviceName}"?\n\nThis will force the device to re-register to obtain a new token.`)) return;

    try {
        const response = await fetch(`/api/devices/${deviceId}/revoke-token`, {
            method: 'POST',
            credentials: 'include'
        });

        if (response.ok) {
            showAlert('Device token revoked successfully', 'success');
            await loadDevices();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to revoke device token', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error revoking device token', 'error');
    }
}

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
            buildStatsCards(); // Update stats cards
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
    if (!confirm(`Delete all photos and records for "${personName}"?\n\nThis will:\n- Remove the face from CodeProject.AI server(s)\n- Delete all photo files\n- Remove all database records\n\nThis cannot be undone.`)) return;

    try {
        const response = await fetch(`/api/registered-faces/${encodeURIComponent(personName)}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        if (response.ok) {
            const data = await response.json();
            showAlert(`Successfully deleted ${personName} (${data.records_deleted} records, ${data.files_deleted} files)`, 'success');

            // Reload registered faces and overview stats
            await loadOverview();
            await loadRegisteredFaces();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to delete face', 'error');
        }
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

async function approveUser(userId, email) {
    if (!confirm(`Approve user ${email}?\n\nThis will activate their account and allow them to log in.`)) return;

    try {
        const response = await fetch(`/api/admin/users/${userId}/activate`, {
            method: 'POST',
            credentials: 'include'
        });

        if (response.ok) {
            showAlert('User approved successfully', 'success');
            await loadOverview();
            await loadUsers();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to approve user', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error approving user', 'error');
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
                                            onclick="removeUserFromLocation(${userId}, ${loc.location_id})">Remove</button>
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

async function removeUserFromLocation(userId, locationId) {
    if (!confirm('Remove user from this location?')) return;

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
async function changeManagementLocation() {
    const select = document.getElementById('managedLocationSelect');
    managedLocationFilter = select.value ? parseInt(select.value) : null;

    console.log('Location filter changed to:', managedLocationFilter || 'All Locations');

    // Reload overview stats with new filter
    await loadOverview();

    // Rebuild stats cards and tabs with updated counts
    buildStatsCards();
    buildTabs();

    // Reload current tab with new filter
    if (activeTab) {
        await loadTabData(activeTab);
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
