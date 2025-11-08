// Management Dashboard - Role-Aware Interface
// Handles both superadmin and location admin views

let currentUser = null;
let overviewStats = null;
let allLocations = [];
let allServers = [];
let allRelays = []; // Store all WebRTC relays
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
    const devicesBadge = overviewStats.total_devices > 0
        ? `<span class="badge-count info">${overviewStats.total_devices}</span>`
        : '';
    tabs.push(`
        <button class="tab-button ${devicesActive}" onclick="switchTab('devices')">
            📱 Devices${devicesBadge}
        </button>
    `);

    const facesActive = currentActive === 'faces' ? 'active' : '';
    const facesBadge = overviewStats.total_registered_faces > 0
        ? `<span class="badge-count info">${overviewStats.total_registered_faces}</span>`
        : '';
    tabs.push(`
        <button class="tab-button ${facesActive}" onclick="switchTab('faces')">
            👥 Registered Faces${facesBadge}
        </button>
    `);

    // Categories & Tags tab (all admins)
    const categoriesActive = currentActive === 'categories' ? 'active' : '';
    const categoriesBadge = overviewStats.total_categories > 0
        ? `<span class="badge-count info">${overviewStats.total_categories}</span>`
        : '';
    tabs.push(`
        <button class="tab-button ${categoriesActive}" onclick="switchTab('categories')">
            🏷️ Categories & Tags${categoriesBadge}
        </button>
    `);

    // Superadmin-only tabs
    if (overviewStats.is_superuser) {
        const usersActive = currentActive === 'users' ? 'active' : '';
        const usersBadge = overviewStats.total_users > 0
            ? `<span class="badge-count info">${overviewStats.total_users}</span>`
            : '';
        tabs.push(`
            <button class="tab-button ${usersActive}" onclick="switchTab('users')">
                👤 Users${usersBadge}
            </button>
        `);

        const locationsActive = currentActive === 'locations' ? 'active' : '';
        const locationsBadge = overviewStats.total_locations > 0
            ? `<span class="badge-count info">${overviewStats.total_locations}</span>`
            : '';
        tabs.push(`
            <button class="tab-button ${locationsActive}" onclick="switchTab('locations')">
                📍 Locations${locationsBadge}
            </button>
        `);

        const serversActive = currentActive === 'servers' ? 'active' : '';
        const serversBadge = overviewStats.total_servers > 0
            ? `<span class="badge-count info">${overviewStats.total_servers}</span>`
            : '';
        tabs.push(`
            <button class="tab-button ${serversActive}" onclick="switchTab('servers')">
                🖥️ Servers${serversBadge}
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
        case 'categories':
            await loadCategories();
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
                await loadRelays();
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
                        <th>Last Seen</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${devices.map(device => {
                        const lastSeen = device.last_seen
                            ? formatUTCDateTimeLocal(device.last_seen)
                            : '<span style="color: #999;">Never</span>';
                        return `
                            <tr>
                                <td><strong style="font-size: 18px; letter-spacing: 2px; font-family: monospace;">${escapeHtml(device.registration_code)}</strong></td>
                                <td>${formatUTCDateTimeLocal(device.registered_at)}</td>
                                <td>${lastSeen}</td>
                                <td>
                                    <button class="btn btn-success" onclick="showApproveDeviceModal('${device.device_id}', '${escapeHtml(device.registration_code)}')">Approve</button>
                                    <button class="btn btn-danger" onclick="rejectDevice('${device.device_id}')">Reject</button>
                                </td>
                            </tr>
                        `;
                    }).join('')}
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
                        <th>Area</th>
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
                        // Escape single quotes for JavaScript onclick handlers
                        const jsEscapedName = device.device_name.replace(/'/g, "\\'");

                        return `
                        <tr>
                            <td><strong>${escapeHtml(device.device_name)}</strong></td>
                            <td><span class="badge badge-info">${escapeHtml(device.device_type)}</span></td>
                            <td>${escapeHtml(device.location_name || 'Unknown')}</td>
                            <td>${device.area_name ? escapeHtml(device.area_name) : '<span style="color: #999;">N/A</span>'}</td>
                            <td>${device.last_seen ? formatUTCDateTimeLocal(device.last_seen) : 'Never'}</td>
                            <td><span class="badge ${tokenBadgeClass}">${tokenDisplay}</span></td>
                            <td>
                                <button class="btn btn-warning btn-sm" onclick="editDeviceById('${device.device_id}')">Edit</button>
                                ${tokenStatus === 'active' ? `<button class="btn btn-secondary btn-sm" onclick="revokeDeviceToken('${device.device_id}', '${jsEscapedName}')">Revoke Token</button>` : ''}
                                <button class="btn btn-danger btn-sm" onclick="deleteDevice('${device.device_id}', '${jsEscapedName}')">Delete</button>
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
                        ${face.registered_at ? `<p style="font-size: 12px; color: #666; margin-top: 5px;">Registered: ${formatDateLocal(face.registered_at)}</p>` : ''}
                        ${face.user_expiration ? `<p style="font-size: 12px; color: ${face.user_expiration === 'never' ? '#28a745' : '#666'}; margin-top: 2px;">Expires: ${face.user_expiration === 'never' ? 'Never' : formatDateLocal(face.user_expiration)} <button onclick="showEditExpirationModal('${escapeHtml(face.person_id)}', '${escapeHtml(face.person_name)}', '${escapeHtml(face.user_expiration)}')" style="background: none; border: none; color: #667eea; cursor: pointer; font-size: 12px; padding: 0; margin-left: 5px;">✏️</button></p>` : ''}
                        <p style="margin-top: 8px;">
                            <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; user-select: none;">
                                <input type="checkbox"
                                       ${face.is_employee ? 'checked' : ''}
                                       onchange="updateEmployeeStatus('${escapeHtml(face.person_id)}', '${escapeHtml(face.person_name)}', this.checked)"
                                       style="cursor: pointer;">
                                <span>Employee</span>
                            </label>
                        </p>
                        <button class="btn btn-secondary btn-sm" style="margin-top: 10px; width: 100%;"
                                onclick="showAssignTagsModal('${escapeHtml(face.person_id)}', '${escapeHtml(face.person_name)}', ${face.location_id})">🏷️ Assign Tags</button>
                        <button class="btn btn-primary btn-sm" style="margin-top: 5px; width: 100%;"
                                data-person-id="${escapeHtml(face.person_id)}"
                                data-person-name="${escapeHtml(face.person_name)}"
                                data-photos='${JSON.stringify(face.all_photos)}'
                                onclick="showEditPhotosModalFromButton(this)">✂️ Edit Photos</button>
                        <button class="btn btn-danger btn-sm" style="margin-top: 5px; width: 100%;"
                                onclick="deleteFaceFromDatabase('${escapeHtml(face.person_id)}', '${escapeHtml(face.person_name)}')">Delete</button>
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
                    ${allLocations.map(location => {
                        // Escape single quotes for JavaScript onclick handlers
                        const jsEscapedName = location.name.replace(/'/g, "\\'");
                        return `
                        <tr>
                            <td><strong>${escapeHtml(location.name)}</strong></td>
                            <td>${escapeHtml(location.address || 'N/A')}</td>
                            <td>${escapeHtml(location.description || 'N/A')}</td>
                            <td>
                                <button class="btn btn-secondary btn-sm" onclick="showEditLocationModal(${location.id})">Edit</button>
                                <button class="btn btn-primary btn-sm" onclick="manageAreas(${location.id}, '${jsEscapedName}')">Areas</button>
                                <button class="btn btn-danger btn-sm" onclick="deleteLocation(${location.id}, '${jsEscapedName}')">Delete</button>
                            </td>
                        </tr>
                        `;
                    }).join('')}
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
                                <button class="btn btn-secondary btn-sm" onclick="testServerConnection(${server.id})">Test</button>
                                <button class="btn btn-secondary btn-sm" onclick="showEditServerModal(${server.id})">Edit</button>
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

async function testServerConnection(serverId) {
    const server = allServers.find(s => s.id === serverId);
    if (!server) {
        showAlert('Server not found', 'error');
        return;
    }

    // Open modal and set title
    document.getElementById('test-connection-title').textContent = `${server.friendly_name} - Connection Test`;
    const resultsDiv = document.getElementById('test-connection-results');

    // Initial status
    resultsDiv.innerHTML = `
        <div style="font-size: 16px; font-weight: bold; margin-bottom: 15px; color: #0c5460;">
            Testing endpoints...
        </div>
        <div id="test-progress" style="line-height: 1.8;">
            <div>⏳ Preparing to test endpoints...</div>
        </div>
    `;

    openModal('test-connection-modal');

    const progressDiv = document.getElementById('test-progress');

    try {
        // Update progress: Starting tests
        progressDiv.innerHTML = '<div>⏳ Contacting server and running tests...</div>';

        const response = await fetch(`/api/codeproject-servers/${serverId}/test`, {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const result = await response.json();

        // Determine overall status
        const configuredTests = Object.values(result.tests).filter(t => !t.not_configured);
        const anyOnline = configuredTests.some(t => t.online);
        const hasAuthFailure = Object.values(result.tests).some(t => t.auth_failed);

        // Build results display
        let statusColor = anyOnline ? '#155724' : (hasAuthFailure ? '#721c24' : '#856404');
        let statusBg = anyOnline ? '#d4edda' : (hasAuthFailure ? '#f8d7da' : '#fff3cd');

        let html = `
            <div style="padding: 15px; background: ${statusBg}; border-radius: 6px; margin-bottom: 20px;">
                <div style="font-size: 16px; font-weight: bold; color: ${statusColor};">
                    ${result.summary}
                </div>
            </div>
            <div style="line-height: 1.8;">
        `;

        // Public Endpoint
        if (result.tests.public) {
            const test = result.tests.public;
            if (test.not_configured) {
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: #f8f9fa; border-left: 4px solid #6c757d; border-radius: 4px;">
                        <div style="font-weight: bold; margin-bottom: 5px;">○ Public Endpoint</div>
                        <div style="color: #6c757d; font-style: italic; margin-left: 20px;">Not configured</div>
                    </div>
                `;
            } else {
                const icon = test.online ? '✓' : '✗';
                const borderColor = test.online ? '#28a745' : '#dc3545';
                const bgColor = test.online ? '#f8fff9' : '#fff5f5';
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: ${bgColor}; border-left: 4px solid ${borderColor}; border-radius: 4px;">
                        <div style="font-weight: bold; margin-bottom: 5px;">${icon} Public Endpoint</div>
                        <div style="margin-left: 20px;">${test.online ? 'Online and responding' : (test.auth_failed ? 'Authentication failed (401 Unauthorized)' : test.message.replace('✗ Public endpoint', '').replace('endpoint ', ''))}</div>
                        ${test.response_time_ms ? `<div style="margin-left: 20px; font-size: 13px; color: #666;">Response time: ${test.response_time_ms}ms</div>` : ''}
                    </div>
                `;
            }
        }

        // LAN Endpoint
        if (result.tests.lan) {
            const test = result.tests.lan;
            if (test.not_configured) {
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: #f8f9fa; border-left: 4px solid #6c757d; border-radius: 4px;">
                        <div style="font-weight: bold; margin-bottom: 5px;">○ LAN Endpoint</div>
                        <div style="color: #6c757d; font-style: italic; margin-left: 20px;">Not configured</div>
                    </div>
                `;
            } else {
                const icon = test.online ? '✓' : '✗';
                const borderColor = test.online ? '#28a745' : '#dc3545';
                const bgColor = test.online ? '#f8fff9' : '#fff5f5';
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: ${bgColor}; border-left: 4px solid ${borderColor}; border-radius: 4px;">
                        <div style="font-weight: bold; margin-bottom: 5px;">${icon} LAN Endpoint</div>
                        <div style="margin-left: 20px;">${test.online ? 'Online and responding' : test.message.replace('✗ LAN endpoint', '').replace('endpoint ', '')}</div>
                        ${test.response_time_ms ? `<div style="margin-left: 20px; font-size: 13px; color: #666;">Response time: ${test.response_time_ms}ms</div>` : ''}
                    </div>
                `;
            }
        }

        // Legacy Endpoint
        if (result.tests.legacy) {
            const test = result.tests.legacy;
            const icon = test.online ? '✓' : '✗';
            const borderColor = test.online ? '#28a745' : '#dc3545';
            const bgColor = test.online ? '#f8fff9' : '#fff5f5';
            html += `
                <div style="margin-bottom: 15px; padding: 12px; background: ${bgColor}; border-left: 4px solid ${borderColor}; border-radius: 4px;">
                    <div style="font-weight: bold; margin-bottom: 5px;">${icon} Legacy Endpoint</div>
                    <div style="margin-left: 20px;">${test.online ? 'Online and responding' : test.message.replace('✗ Legacy endpoint', '').replace('endpoint ', '')}</div>
                    ${test.response_time_ms ? `<div style="margin-left: 20px; font-size: 13px; color: #666;">Response time: ${test.response_time_ms}ms</div>` : ''}
                </div>
            `;
        }

        html += '</div>';
        resultsDiv.innerHTML = html;

    } catch (error) {
        console.error('Error testing server:', error);
        resultsDiv.innerHTML = `
            <div style="padding: 15px; background: #f8d7da; border-radius: 6px; color: #721c24;">
                <div style="font-weight: bold; margin-bottom: 10px;">Connection Test Failed</div>
                <div>${escapeHtml(error.message)}</div>
            </div>
        `;
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
        document.getElementById('edit-device-server'),
        document.getElementById('location-server'),
        document.getElementById('edit-location-server')
    ];

    selects.forEach(select => {
        if (select) {
            const currentValue = select.value;
            // Location server selects allow "None" option
            const isLocationServer = select.id === 'location-server' || select.id === 'edit-location-server';
            const defaultOption = isLocationServer
                ? '<option value="">None (will use first available)</option>'
                : '<option value="">Select a server...</option>';

            select.innerHTML = defaultOption +
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
// Load areas when location changes in approve device form
document.getElementById('approve-device-location').addEventListener('change', async (e) => {
    const locationId = e.target.value;
    const areaSelect = document.getElementById('approve-device-area');

    // Clear and reset area dropdown
    areaSelect.innerHTML = '<option value="">No area assigned</option>';

    if (!locationId) return;

    try {
        const response = await fetch(`/api/locations/${locationId}/areas`, {
            credentials: 'include'
        });

        if (response.ok) {
            const data = await response.json();
            const areas = data.areas || [];

            areas.forEach(area => {
                const option = document.createElement('option');
                option.value = area.id;
                option.textContent = area.area_name;
                areaSelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading areas:', error);
    }
});

document.getElementById('approve-device-type').addEventListener('change', (e) => {
    const serverGroup = document.getElementById('approve-device-server-group');
    const serverSelect = document.getElementById('approve-device-server');
    const processingMode = document.getElementById('approve-device-processing-mode');
    const scannerSettings = document.getElementById('approve-device-scanner-settings');
    const dashboardSettings = document.getElementById('approve-device-dashboard-settings');

    // Server is always hidden in approve modal - auto-assigned based on location
    serverGroup.style.display = 'none';
    serverSelect.removeAttribute('required');

    if (e.target.value === 'location_dashboard') {
        processingMode.style.display = 'none';
        scannerSettings.style.display = 'none';
        dashboardSettings.style.display = 'block';
    } else {
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

    const areaId = document.getElementById('approve-device-area').value;

    const data = {
        device_name: document.getElementById('approve-device-name').value,
        location_id: parseInt(document.getElementById('approve-device-location').value),
        area_id: areaId ? parseInt(areaId) : null,
        device_type: deviceType,
        // Server will be auto-assigned based on location's server or first available
        codeproject_server_id: null
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

    // Load areas for the device's location
    const areaSelect = document.getElementById('edit-device-area');
    areaSelect.innerHTML = '<option value="">No area assigned</option>';
    if (device.location_id) {
        try {
            const response = await fetch(`/api/locations/${device.location_id}/areas`, {
                credentials: 'include'
            });
            if (response.ok) {
                const data = await response.json();
                const areas = data.areas || [];
                areas.forEach(area => {
                    const option = document.createElement('option');
                    option.value = area.id;
                    option.textContent = area.area_name;
                    if (device.area_id && area.id === device.area_id) {
                        option.selected = true;
                    }
                    areaSelect.appendChild(option);
                });
            }
        } catch (error) {
            console.error('Error loading areas:', error);
        }
    }

    // Select the server if device has one
    if (device.codeproject_server_id) {
        document.getElementById('edit-device-server').value = device.codeproject_server_id;
    }

    // Show/hide server dropdown and processing mode based on device type
    const serverGroup = document.getElementById('edit-device-server-group');
    const serverSelect = document.getElementById('edit-device-server');
    const processingMode = document.getElementById('edit-device-processing-mode');
    const scannerSettings = document.getElementById('edit-device-scanner-settings');
    const dashboardSettings = document.getElementById('edit-device-dashboard-settings');

    if (device.device_type === 'location_dashboard') {
        serverGroup.style.display = 'none';
        serverSelect.removeAttribute('required');
        processingMode.style.display = 'none';
        scannerSettings.style.display = 'none';
        dashboardSettings.style.display = 'block';
        // Populate dashboard settings
        document.getElementById('edit-device-dashboard-timeout').value = device.dashboard_display_timeout_minutes || '';
    } else {
        dashboardSettings.style.display = 'none';
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

// Load areas when location changes in edit device form
document.getElementById('edit-device-location').addEventListener('change', async (e) => {
    const locationId = e.target.value;
    const areaSelect = document.getElementById('edit-device-area');

    // Clear and reset area dropdown
    areaSelect.innerHTML = '<option value="">No area assigned</option>';

    if (!locationId) return;

    try {
        const response = await fetch(`/api/locations/${locationId}/areas`, {
            credentials: 'include'
        });

        if (response.ok) {
            const data = await response.json();
            const areas = data.areas || [];

            areas.forEach(area => {
                const option = document.createElement('option');
                option.value = area.id;
                option.textContent = area.area_name;
                areaSelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading areas:', error);
    }
});

document.getElementById('edit-device-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const deviceId = document.getElementById('edit-device-id').value;
    const deviceType = document.getElementById('edit-device-type').value;
    const serverId = document.getElementById('edit-device-server').value;
    const areaId = document.getElementById('edit-device-area').value;

    const data = {
        device_name: document.getElementById('edit-device-name').value,
        location_id: parseInt(document.getElementById('edit-device-location').value),
        area_id: areaId ? parseInt(areaId) : null,
        device_type: deviceType,
        codeproject_server_id: deviceType === 'location_dashboard' ? null : (serverId ? parseInt(serverId) : null)
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
async function deleteFaceFromDatabase(personId, personName) {
    if (!confirm(`Delete all photos and records for "${personName}"?\n\nThis will:\n- Remove the face from CodeProject.AI server(s)\n- Delete all photo files\n- Remove all database records\n\nThis cannot be undone.`)) return;

    try {
        const response = await fetch(`/api/registered-faces/${encodeURIComponent(personId)}`, {
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

// Update employee status for a registered face
async function updateEmployeeStatus(personId, personName, isEmployee) {
    try {
        const response = await fetch(`/api/registered-faces/${encodeURIComponent(personId)}/employee-status?is_employee=${isEmployee}`, {
            method: 'PUT',
            credentials: 'include'
        });

        if (response.ok) {
            const data = await response.json();
            showAlert(`Updated ${personName} to ${isEmployee ? 'employee' : 'visitor'}`, 'success');
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to update employee status', 'error');
            // Reload to restore checkbox state
            await loadRegisteredFaces();
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error updating employee status', 'error');
        // Reload to restore checkbox state
        await loadRegisteredFaces();
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

async function showEditLocationModal(locationId) {
    // Find the location in allLocations
    const location = allLocations.find(loc => loc.id === locationId);
    if (!location) {
        showAlert('Location not found', 'error');
        return;
    }

    // Populate the form
    document.getElementById('edit-location-id').value = location.id;
    document.getElementById('edit-location-name').value = location.name;
    document.getElementById('edit-location-address').value = location.address || '';
    document.getElementById('edit-location-description').value = location.description || '';
    document.getElementById('edit-location-timezone').value = location.timezone || 'UTC';
    document.getElementById('edit-location-contact').value = location.contact_info || '';

    // Set the server dropdown
    const serverSelect = document.getElementById('edit-location-server');
    if (location.codeproject_server_id) {
        serverSelect.value = location.codeproject_server_id;
    } else {
        serverSelect.value = '';
    }

    // Set the relay dropdown
    const relaySelect = document.getElementById('edit-location-relay');
    if (location.webrtc_relay_id) {
        relaySelect.value = location.webrtc_relay_id;
    } else {
        relaySelect.value = '';
    }

    openModal('edit-location-modal');
}

document.getElementById('create-location-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const serverValue = document.getElementById('location-server').value;
    const relayValue = document.getElementById('location-relay').value;
    const data = {
        name: document.getElementById('location-name').value,
        address: document.getElementById('location-address').value || null,
        description: document.getElementById('location-description').value || null,
        timezone: document.getElementById('location-timezone').value || 'UTC',
        contact_info: document.getElementById('location-contact').value || null,
        codeproject_server_id: serverValue ? parseInt(serverValue) : null,
        webrtc_relay_id: relayValue ? parseInt(relayValue) : null
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

document.getElementById('edit-location-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const locationId = document.getElementById('edit-location-id').value;
    const serverValue = document.getElementById('edit-location-server').value;
    const relayValue = document.getElementById('edit-location-relay').value;
    const data = {
        name: document.getElementById('edit-location-name').value,
        address: document.getElementById('edit-location-address').value || null,
        description: document.getElementById('edit-location-description').value || null,
        timezone: document.getElementById('edit-location-timezone').value || 'UTC',
        contact_info: document.getElementById('edit-location-contact').value || null,
        codeproject_server_id: serverValue ? parseInt(serverValue) : null,
        webrtc_relay_id: relayValue ? parseInt(relayValue) : null
    };

    try {
        const response = await fetch(`/api/locations/${locationId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showAlert('Location updated successfully', 'success');
            closeModal('edit-location-modal');
            await loadOverview();
            await loadLocations();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to update location', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error updating location', 'error');
    }
});

// Server management (superadmin only)
function showCreateServerModal() {
    document.getElementById('create-server-form').reset();
    // Reset auth fields visibility
    document.getElementById('server-auth-fields').style.display = 'none';
    document.getElementById('server-auth-username').required = false;
    document.getElementById('server-auth-password').required = false;
    openModal('create-server-modal');
}

// Toggle auth fields visibility in create server form
document.getElementById('server-auth-enabled').addEventListener('change', (e) => {
    const authFields = document.getElementById('server-auth-fields');
    authFields.style.display = e.target.checked ? 'block' : 'none';

    // Make username/password required when auth is enabled
    document.getElementById('server-auth-username').required = e.target.checked;
    document.getElementById('server-auth-password').required = e.target.checked;
});

// Toggle auth fields visibility in edit server form
document.getElementById('edit-server-auth-enabled').addEventListener('change', (e) => {
    const authFields = document.getElementById('edit-server-auth-fields');
    authFields.style.display = e.target.checked ? 'block' : 'none';
});

document.getElementById('create-server-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const authEnabled = document.getElementById('server-auth-enabled').checked;
    const data = {
        friendly_name: document.getElementById('server-name').value,
        endpoint_url: document.getElementById('server-url').value,
        public_endpoint_url: document.getElementById('server-public-url').value || null,
        lan_endpoint_url: document.getElementById('server-lan-url').value || null,
        server_communication_preference: document.getElementById('server-comm-preference').value,
        description: document.getElementById('server-description').value || null,
        auth_enabled: authEnabled,
        auth_username: authEnabled ? document.getElementById('server-auth-username').value : null,
        auth_password: authEnabled ? document.getElementById('server-auth-password').value : null
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

function showEditServerModal(serverId) {
    // Find the server in the allServers array
    const server = allServers.find(s => s.id === serverId);

    if (!server) {
        showAlert('Server not found', 'error');
        return;
    }

    // Populate the form fields
    document.getElementById('edit-server-id').value = server.id;
    document.getElementById('edit-server-name').value = server.friendly_name;
    document.getElementById('edit-server-url').value = server.endpoint_url;
    document.getElementById('edit-server-public-url').value = server.public_endpoint_url || '';
    document.getElementById('edit-server-lan-url').value = server.lan_endpoint_url || '';
    document.getElementById('edit-server-comm-preference').value = server.server_communication_preference || 'lan';
    document.getElementById('edit-server-description').value = server.description || '';

    // Set auth fields
    document.getElementById('edit-server-auth-enabled').checked = server.auth_enabled || false;
    document.getElementById('edit-server-auth-username').value = server.auth_username || '';
    document.getElementById('edit-server-auth-password').value = ''; // Always blank for security

    // Show/hide auth fields based on current state
    document.getElementById('edit-server-auth-fields').style.display = server.auth_enabled ? 'block' : 'none';

    openModal('edit-server-modal');
}

document.getElementById('edit-server-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const serverId = document.getElementById('edit-server-id').value;
    const authEnabled = document.getElementById('edit-server-auth-enabled').checked;
    const password = document.getElementById('edit-server-auth-password').value;

    const data = {
        friendly_name: document.getElementById('edit-server-name').value,
        endpoint_url: document.getElementById('edit-server-url').value,
        public_endpoint_url: document.getElementById('edit-server-public-url').value || null,
        lan_endpoint_url: document.getElementById('edit-server-lan-url').value || null,
        server_communication_preference: document.getElementById('edit-server-comm-preference').value,
        description: document.getElementById('edit-server-description').value || null,
        auth_enabled: authEnabled,
        auth_username: authEnabled ? document.getElementById('edit-server-auth-username').value : null,
        auth_password: password || null  // Only send if changed
    };

    try {
        const response = await fetch(`/api/codeproject-servers/${serverId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showAlert('Server updated successfully', 'success');
            closeModal('edit-server-modal');
            await loadServers();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to update server', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error updating server', 'error');
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

// ============================================================================
// WebRTC RELAY MANAGEMENT
// ============================================================================

async function loadRelays() {
    try {
        await loadRelaysData();

        const container = document.getElementById('webrtc-relays-container');

        if (allRelays.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="icon">📡</div><p>No WebRTC relays configured</p></div>';
            return;
        }

        container.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Endpoints</th>
                        <th>Description</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${allRelays.map(relay => {
                        const endpoints = [];
                        if (relay.public_endpoint_url) endpoints.push(`Public: ${relay.public_endpoint_url}`);
                        if (relay.lan_endpoint_url) endpoints.push(`LAN: ${relay.lan_endpoint_url}`);
                        const endpointText = endpoints.join('<br>') || 'No endpoints';

                        return `
                            <tr>
                                <td><strong>${escapeHtml(relay.friendly_name)}</strong></td>
                                <td style="font-size: 12px;">${endpointText}</td>
                                <td>${escapeHtml(relay.description || 'N/A')}</td>
                                <td>
                                    <button class="btn btn-secondary btn-sm" onclick="testRelayConnection(${relay.id})">Test</button>
                                    <button class="btn btn-secondary btn-sm" onclick="showEditRelayModal(${relay.id})">Edit</button>
                                    <button class="btn btn-danger btn-sm" onclick="deleteRelay(${relay.id}, '${escapeHtml(relay.friendly_name)}')">Delete</button>
                                </td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        `;
    } catch (error) {
        console.error('Error loading relays:', error);
        showAlert('Failed to load WebRTC relays', 'error');
    }
}

async function loadRelaysData() {
    const response = await fetch('/api/webrtc-relays', { credentials: 'include' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    allRelays = await response.json();
    updateRelayDropdowns();
}

function updateRelayDropdowns() {
    const selects = [
        document.getElementById('location-relay'),
        document.getElementById('edit-location-relay')
    ];

    selects.forEach(select => {
        if (!select) return;

        const currentValue = select.value;
        const firstOption = select.options[0]; // Preserve first "None" option

        select.innerHTML = '';
        if (firstOption) select.appendChild(firstOption.cloneNode(true));

        allRelays.forEach(relay => {
            const option = document.createElement('option');
            option.value = relay.id;
            option.textContent = relay.friendly_name;
            select.appendChild(option);
        });

        if (currentValue) select.value = currentValue;
    });
}

async function testRelayConnection(relayId) {
    const relay = allRelays.find(r => r.id === relayId);
    if (!relay) {
        showAlert('Relay not found', 'error');
        return;
    }

    // Open modal and set title
    document.getElementById('test-connection-title').textContent = `${relay.friendly_name} - Connection Test`;
    const resultsDiv = document.getElementById('test-connection-results');

    // Initial status
    resultsDiv.innerHTML = `
        <div style="font-size: 16px; font-weight: bold; margin-bottom: 15px; color: #0c5460;">
            Testing endpoints...
        </div>
        <div id="test-progress" style="line-height: 1.8;">
            <div>⏳ Preparing to test endpoints...</div>
        </div>
    `;

    openModal('test-connection-modal');

    const progressDiv = document.getElementById('test-progress');

    try {
        // Update progress: Starting tests
        progressDiv.innerHTML = '<div>⏳ Contacting relay and running tests...</div>';

        const response = await fetch(`/api/webrtc-relays/${relayId}/test`, {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const result = await response.json();

        // Determine overall status
        const configuredTests = Object.values(result.tests).filter(t => !t.not_configured);
        const anyOnline = configuredTests.some(t => t.online);
        const hasAuthFailure = Object.values(result.tests).some(t => t.auth_failed);

        // Build results display
        let statusColor = anyOnline ? '#155724' : (hasAuthFailure ? '#721c24' : '#856404');
        let statusBg = anyOnline ? '#d4edda' : (hasAuthFailure ? '#f8d7da' : '#fff3cd');

        let html = `
            <div style="padding: 15px; background: ${statusBg}; border-radius: 6px; margin-bottom: 20px;">
                <div style="font-size: 16px; font-weight: bold; color: ${statusColor};">
                    ${result.summary}
                </div>
            </div>
            <div style="line-height: 1.8;">
        `;

        // Public Endpoint
        if (result.tests.public) {
            const test = result.tests.public;
            if (test.not_configured) {
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: #f8f9fa; border-left: 4px solid #6c757d; border-radius: 4px;">
                        <div style="font-weight: bold; margin-bottom: 5px;">○ Public Endpoint</div>
                        <div style="color: #6c757d; font-style: italic; margin-left: 20px;">Not configured</div>
                    </div>
                `;
            } else {
                const icon = test.online ? '✓' : '✗';
                const borderColor = test.online ? '#28a745' : '#dc3545';
                const bgColor = test.online ? '#f8fff9' : '#fff5f5';
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: ${bgColor}; border-left: 4px solid ${borderColor}; border-radius: 4px;">
                        <div style="font-weight: bold; margin-bottom: 5px;">${icon} Public Endpoint</div>
                        <div style="margin-left: 20px;">${test.message.replace('✓ Public endpoint', '').replace('✗ Public endpoint', '').trim()}</div>
                        ${test.response_time_ms ? `<div style="margin-left: 20px; font-size: 13px; color: #666;">Response time: ${test.response_time_ms}ms</div>` : ''}
                    </div>
                `;
            }
        }

        // LAN Endpoint
        if (result.tests.lan) {
            const test = result.tests.lan;
            if (test.not_configured) {
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: #f8f9fa; border-left: 4px solid #6c757d; border-radius: 4px;">
                        <div style="font-weight: bold; margin-bottom: 5px;">○ LAN Endpoint</div>
                        <div style="color: #6c757d; font-style: italic; margin-left: 20px;">Not configured</div>
                    </div>
                `;
            } else {
                const icon = test.online ? '✓' : '✗';
                const borderColor = test.online ? '#28a745' : '#dc3545';
                const bgColor = test.online ? '#f8fff9' : '#fff5f5';
                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: ${bgColor}; border-left: 4px solid ${borderColor}; border-radius: 4px;">
                        <div style="font-weight: bold; margin-bottom: 5px;">${icon} LAN Endpoint</div>
                        <div style="margin-left: 20px;">${test.message.replace('✓ LAN endpoint', '').replace('✗ LAN endpoint', '').trim()}</div>
                        ${test.response_time_ms ? `<div style="margin-left: 20px; font-size: 13px; color: #666;">Response time: ${test.response_time_ms}ms</div>` : ''}
                    </div>
                `;
            }
        }

        html += '</div>';
        resultsDiv.innerHTML = html;

    } catch (error) {
        console.error('Error testing relay:', error);
        resultsDiv.innerHTML = `
            <div style="padding: 15px; background: #f8d7da; border-radius: 6px; color: #721c24;">
                <div style="font-weight: bold; margin-bottom: 10px;">Connection Test Failed</div>
                <div>${escapeHtml(error.message)}</div>
            </div>
        `;
    }
}

function showCreateRelayModal() {
    document.getElementById('create-relay-form').reset();
    // Reset auth fields visibility
    document.getElementById('relay-auth-fields').style.display = 'none';
    document.getElementById('relay-auth-username').required = false;
    document.getElementById('relay-auth-password').required = false;
    openModal('create-relay-modal');
}

function toggleRelayAuthFields(mode) {
    const checkbox = document.getElementById(mode === 'create' ? 'relay-auth-enabled' : 'edit-relay-auth-enabled');
    const authFields = document.getElementById(mode === 'create' ? 'relay-auth-fields' : 'edit-relay-auth-fields');
    authFields.style.display = checkbox.checked ? 'block' : 'none';

    if (mode === 'create') {
        document.getElementById('relay-auth-username').required = checkbox.checked;
        document.getElementById('relay-auth-password').required = checkbox.checked;
    }
}

document.getElementById('create-relay-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const authEnabled = document.getElementById('relay-auth-enabled').checked;
    const data = {
        friendly_name: document.getElementById('relay-name').value,
        public_endpoint_url: document.getElementById('relay-public-url').value || null,
        lan_endpoint_url: document.getElementById('relay-lan-url').value || null,
        server_communication_preference: document.getElementById('relay-comm-preference').value,
        description: document.getElementById('relay-description').value || null,
        auth_enabled: authEnabled,
        auth_username: authEnabled ? document.getElementById('relay-auth-username').value : null,
        auth_password: authEnabled ? document.getElementById('relay-auth-password').value : null
    };

    try {
        const response = await fetch('/api/webrtc-relays', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showAlert('WebRTC relay added successfully', 'success');
            closeModal('create-relay-modal');
            await loadRelays();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to add relay', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error adding relay', 'error');
    }
});

function showEditRelayModal(relayId) {
    // Find the relay in the allRelays array
    const relay = allRelays.find(r => r.id === relayId);

    if (!relay) {
        showAlert('Relay not found', 'error');
        return;
    }

    // Populate the form fields
    document.getElementById('edit-relay-id').value = relay.id;
    document.getElementById('edit-relay-name').value = relay.friendly_name;
    document.getElementById('edit-relay-public-url').value = relay.public_endpoint_url || '';
    document.getElementById('edit-relay-lan-url').value = relay.lan_endpoint_url || '';
    document.getElementById('edit-relay-comm-preference').value = relay.server_communication_preference || 'lan';
    document.getElementById('edit-relay-description').value = relay.description || '';

    // Set auth fields
    document.getElementById('edit-relay-auth-enabled').checked = relay.auth_enabled || false;
    document.getElementById('edit-relay-auth-username').value = relay.auth_username || '';
    document.getElementById('edit-relay-auth-password').value = ''; // Always blank for security

    // Show/hide auth fields based on current state
    document.getElementById('edit-relay-auth-fields').style.display = relay.auth_enabled ? 'block' : 'none';

    openModal('edit-relay-modal');
}

document.getElementById('edit-relay-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const relayId = document.getElementById('edit-relay-id').value;
    const authEnabled = document.getElementById('edit-relay-auth-enabled').checked;
    const password = document.getElementById('edit-relay-auth-password').value;

    const data = {
        friendly_name: document.getElementById('edit-relay-name').value,
        public_endpoint_url: document.getElementById('edit-relay-public-url').value || null,
        lan_endpoint_url: document.getElementById('edit-relay-lan-url').value || null,
        server_communication_preference: document.getElementById('edit-relay-comm-preference').value,
        description: document.getElementById('edit-relay-description').value || null,
        auth_enabled: authEnabled,
        auth_username: authEnabled ? document.getElementById('edit-relay-auth-username').value : null,
        auth_password: password || null  // Only send if changed
    };

    try {
        const response = await fetch(`/api/webrtc-relays/${relayId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showAlert('WebRTC relay updated successfully', 'success');
            closeModal('edit-relay-modal');
            await loadRelays();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to update relay', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error updating relay', 'error');
    }
});

async function deleteRelay(relayId, name) {
    if (!confirm(`Delete WebRTC relay "${name}"?`)) return;

    try {
        const response = await fetch(`/api/webrtc-relays/${relayId}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        if (response.ok) {
            showAlert('WebRTC relay deleted successfully', 'success');
            await loadRelays();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to delete relay', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error deleting relay', 'error');
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

function showAlert(message, type = 'success', clearPrevious = false) {
    const container = document.getElementById('alert-container');

    // Clear previous alerts if requested
    if (clearPrevious) {
        container.innerHTML = '';
    }

    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.innerHTML = message;
    container.appendChild(alert);

    setTimeout(() => {
        alert.remove();
    }, 5000);
}

// Edit Expiration Modal
let currentExpirationPersonId = null;
let currentExpirationPersonName = null;

function showEditExpirationModal(personId, personName, currentExpiration) {
    currentExpirationPersonId = personId;
    currentExpirationPersonName = personName;

    document.getElementById('expiration-person-name').textContent = personName;

    // Set current value
    const expirationInput = document.getElementById('expiration-date');
    const neverCheckbox = document.getElementById('expiration-never');

    if (currentExpiration === 'never') {
        neverCheckbox.checked = true;
        expirationInput.disabled = true;
        expirationInput.value = '';
    } else {
        neverCheckbox.checked = false;
        expirationInput.disabled = false;
        expirationInput.value = currentExpiration || '';
    }

    openModal('edit-expiration-modal');
}

function toggleExpirationNever() {
    const expirationInput = document.getElementById('expiration-date');
    const neverCheckbox = document.getElementById('expiration-never');

    if (neverCheckbox.checked) {
        expirationInput.disabled = true;
        expirationInput.value = '';
    } else {
        expirationInput.disabled = false;
    }
}

async function saveExpiration() {
    const neverCheckbox = document.getElementById('expiration-never');
    const expirationInput = document.getElementById('expiration-date');

    let expiration;
    if (neverCheckbox.checked) {
        expiration = 'never';
    } else {
        expiration = expirationInput.value;
        if (!expiration) {
            showAlert('Please select an expiration date or check "Never expires"', 'error');
            return;
        }
    }

    try {
        const response = await fetch(`/api/registered-faces/${encodeURIComponent(currentExpirationPersonId)}/expiration?expiration=${encodeURIComponent(expiration)}`, {
            method: 'PUT',
            credentials: 'include'
        });

        if (response.ok) {
            showAlert(`Updated expiration for ${currentExpirationPersonName}`, 'success');
            closeModal('edit-expiration-modal');
            await loadRegisteredFaces();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to update expiration', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error updating expiration', 'error');
    }
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

// Format date string without timezone issues
function formatDateLocal(dateString) {
    if (!dateString) return '';
    // Parse ISO date string (YYYY-MM-DD or YYYY-MM-DDTHH:mm:ss)
    const parts = dateString.split('T')[0].split('-');
    const year = parseInt(parts[0]);
    const month = parseInt(parts[1]) - 1; // Month is 0-indexed
    const day = parseInt(parts[2]);
    const date = new Date(year, month, day);
    return date.toLocaleDateString();
}

// Format UTC datetime string to local datetime for display
function formatUTCDateTimeLocal(dateString) {
    if (!dateString) return '';
    // If the string doesn't have a Z suffix, add it (backend sends UTC without Z)
    const utcString = dateString.endsWith('Z') ? dateString : dateString + 'Z';
    const date = new Date(utcString);
    return date.toLocaleString();
}

async function logout() {
    try {
        await fetch('/auth/logout', { method: 'POST', credentials: 'include' });
        window.location.href = '/login';
    } catch (error) {
        window.location.href = '/login';
    }
}

// Area Management
let currentLocationId = null;
let currentLocationName = '';

async function manageAreas(locationId, locationName) {
    currentLocationId = locationId;
    currentLocationName = locationName;

    document.getElementById('manage-areas-title').textContent = `Manage Areas - ${locationName}`;
    document.getElementById('create-area-form').style.display = 'none';
    document.getElementById('area-create-form').reset();

    openModal('manage-areas-modal');
    await loadAreas();
}

async function loadAreas() {
    const container = document.getElementById('areas-container');
    container.innerHTML = '<div class="loading"><div class="spinner"></div>Loading areas...</div>';

    try {
        const response = await fetch(`/api/locations/${currentLocationId}/areas`, {
            credentials: 'include'
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        const areas = data.areas || [];

        if (areas.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="icon">📍</div><p>No areas configured for this location</p></div>';
            return;
        }

        container.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Area Name</th>
                        <th>Description</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${areas.map(area => {
                        // Escape single quotes for JavaScript onclick handlers
                        const jsEscapedName = area.area_name.replace(/'/g, "\\'");
                        return `
                        <tr>
                            <td><strong>${escapeHtml(area.area_name)}</strong></td>
                            <td>${escapeHtml(area.description || 'N/A')}</td>
                            <td>
                                <button class="btn btn-danger btn-sm" onclick="deleteArea(${area.id}, '${jsEscapedName}')">Delete</button>
                            </td>
                        </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        `;
    } catch (error) {
        console.error('Error loading areas:', error);
        container.innerHTML = '<div class="alert alert-error">Error loading areas</div>';
    }
}

function showCreateAreaForm() {
    document.getElementById('create-area-form').style.display = 'block';
    document.getElementById('create-area-name').focus();
}

function hideCreateAreaForm() {
    document.getElementById('create-area-form').style.display = 'none';
    document.getElementById('area-create-form').reset();
}

document.getElementById('area-create-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const data = {
        location_id: currentLocationId,
        area_name: document.getElementById('create-area-name').value,
        description: document.getElementById('create-area-description').value || null
    };

    try {
        const response = await fetch('/api/areas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showAlert('Area created successfully', 'success');
            hideCreateAreaForm();
            await loadAreas();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to create area', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error creating area', 'error');
    }
});

async function deleteArea(areaId, areaName) {
    if (!confirm(`Delete area "${areaName}"?\n\nDevices in this area will have their area unset.`)) return;

    try {
        const response = await fetch(`/api/areas/${areaId}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        if (response.ok) {
            showAlert('Area deleted successfully', 'success');
            await loadAreas();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to delete area', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error deleting area', 'error');
    }
}

// Register Face Modal
let registerCameraStream = null;
let registerCapturedPhotos = [];
let registerCurrentPositionIndex = 0;
let registerCapturing = false;
let registerPersonName = '';
let registerLocationId = null;
let registerUploadedPhotos = []; // Array of {file, dataUrl, rotation, cropData}

const registerPositions = [
    { name: 'Center', instruction: 'Look straight ahead' },
    { name: 'Left', instruction: 'Turn your head slightly left' },
    { name: 'Right', instruction: 'Turn your head slightly right' },
    { name: 'Up', instruction: 'Tilt your head slightly up' },
    { name: 'Down', instruction: 'Tilt your head slightly down' }
];

function showRegisterFaceModal() {
    // Reset state
    registerCapturedPhotos = [];
    registerUploadedPhotos = [];
    registerCurrentPositionIndex = 0;
    registerCapturing = false;
    registerPersonName = '';
    registerLocationId = null;

    // Reset form
    document.getElementById('register-person-name').value = '';
    document.getElementById('register-location-select').value = '';
    document.getElementById('register-photo-count').textContent = '0';
    document.getElementById('register-progress-fill').style.width = '0%';
    document.getElementById('register-begin-btn').disabled = false;
    document.getElementById('register-submit-btn').disabled = true;
    document.getElementById('upload-submit-btn').disabled = true;
    document.getElementById('register-guidance-indicator').textContent = '';
    document.getElementById('upload-preview-container').innerHTML = '';

    // Show step 1
    document.querySelectorAll('.register-step').forEach(step => step.classList.remove('active'));
    document.getElementById('register-step-name').classList.add('active');

    // Populate location dropdown
    const locationSelect = document.getElementById('register-location-select');
    locationSelect.innerHTML = '<option value="">Select a location...</option>' +
        allLocations.map(loc => `<option value="${loc.id}">${escapeHtml(loc.name)}</option>`).join('');

    // Auto-select if location filter is active
    if (managedLocationFilter) {
        locationSelect.value = managedLocationFilter;
    }

    openModal('register-face-modal');
}

function closeRegisterFaceModal() {
    stopRegisterCamera();
    closeModal('register-face-modal');
}

document.getElementById('register-name-continue').addEventListener('click', () => {
    registerPersonName = document.getElementById('register-person-name').value.trim();
    registerLocationId = parseInt(document.getElementById('register-location-select').value);

    if (!registerPersonName) {
        showAlert('Please enter a name', 'error');
        return;
    }

    if (!registerLocationId) {
        showAlert('Please select a location', 'error');
        return;
    }

    // Go to method selection step
    goToRegisterStep('method');
});

// Helper function to navigate between register steps
function goToRegisterStep(stepName) {
    document.querySelectorAll('.register-step').forEach(step => step.classList.remove('active'));
    document.getElementById(`register-step-${stepName}`).classList.add('active');

    // Clean up based on step
    if (stepName !== 'camera') {
        stopRegisterCamera();
    }
}

// Choose camera method
document.getElementById('choose-camera-btn').addEventListener('click', () => {
    goToRegisterStep('camera');
    startRegisterCamera();
});

// Choose upload method
document.getElementById('choose-upload-btn').addEventListener('click', () => {
    goToRegisterStep('upload');
    // Reset uploaded photos
    registerUploadedPhotos = [];
    renderUploadedPhotos();
});

// Handle file upload
document.getElementById('upload-photos-input').addEventListener('change', async (e) => {
    const files = Array.from(e.target.files);

    for (const file of files) {
        // Read file as data URL
        const dataUrl = await readFileAsDataURL(file);

        // Add to uploaded photos with default settings
        registerUploadedPhotos.push({
            file: file,
            dataUrl: dataUrl,
            rotation: 0,
            cropData: null  // Will store crop coordinates if user crops
        });
    }

    renderUploadedPhotos();

    // Clear file input so same files can be selected again
    e.target.value = '';
});

// Read file as data URL
function readFileAsDataURL(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => resolve(e.target.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

// Render uploaded photos with preview and controls
function renderUploadedPhotos() {
    const container = document.getElementById('upload-preview-container');
    const submitBtn = document.getElementById('upload-submit-btn');

    if (registerUploadedPhotos.length === 0) {
        container.innerHTML = '<p style="color: #999; text-align: center;">No photos uploaded yet</p>';
        submitBtn.disabled = true;
        return;
    }

    container.innerHTML = registerUploadedPhotos.map((photo, index) => {
        const cropBadge = photo.cropData ? '<span style="background: #667eea; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; margin-left: 8px;">✂️ Cropped</span>' : '';
        return `
            <div class="upload-photo-card" data-index="${index}">
                <canvas id="upload-canvas-${index}" class="upload-photo-preview"></canvas>
                <div class="upload-photo-controls">
                    <button class="btn btn-secondary btn-sm" onclick="openCropModal(${index})">✂️ Crop</button>
                    <button class="btn btn-secondary btn-sm" onclick="rotateUploadPhoto(${index}, -90)">↶ Rotate Left</button>
                    <button class="btn btn-secondary btn-sm" onclick="rotateUploadPhoto(${index}, 90)">↷ Rotate Right</button>
                    <button class="btn btn-danger btn-sm" onclick="removeUploadPhoto(${index})">🗑 Remove</button>
                    <span style="margin-left: auto; color: #666; font-size: 14px;">${escapeHtml(photo.file.name)}${cropBadge}</span>
                </div>
            </div>
        `;
    }).join('');

    // Draw canvases with current rotation
    registerUploadedPhotos.forEach((photo, index) => {
        drawRotatedImage(index);
    });

    // Enable submit if we have photos
    submitBtn.disabled = registerUploadedPhotos.length === 0;
}

// Draw image on canvas with rotation and crop
function drawRotatedImage(index) {
    const photo = registerUploadedPhotos[index];
    const canvas = document.getElementById(`upload-canvas-${index}`);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const img = new Image();

    img.onload = () => {
        const rotation = photo.rotation || 0;
        const isRotated90 = Math.abs(rotation % 180) === 90;

        // Create temporary canvas for rotation
        const tempCanvas = document.createElement('canvas');
        const tempCtx = tempCanvas.getContext('2d');

        if (isRotated90) {
            tempCanvas.width = img.height;
            tempCanvas.height = img.width;
        } else {
            tempCanvas.width = img.width;
            tempCanvas.height = img.height;
        }

        // Draw rotated image to temp canvas
        tempCtx.save();
        tempCtx.translate(tempCanvas.width / 2, tempCanvas.height / 2);
        tempCtx.rotate(rotation * Math.PI / 180);
        tempCtx.drawImage(img, -img.width / 2, -img.height / 2);
        tempCtx.restore();

        // Apply crop if exists
        if (photo.cropData) {
            const crop = photo.cropData;
            canvas.width = crop.width;
            canvas.height = crop.height;
            ctx.drawImage(
                tempCanvas,
                crop.x, crop.y, crop.width, crop.height,
                0, 0, crop.width, crop.height
            );
        } else {
            // No crop - just display rotated image
            canvas.width = tempCanvas.width;
            canvas.height = tempCanvas.height;
            ctx.drawImage(tempCanvas, 0, 0);
        }
    };

    img.src = photo.dataUrl;
}

// Rotate uploaded photo
function rotateUploadPhoto(index, degrees) {
    registerUploadedPhotos[index].rotation = (registerUploadedPhotos[index].rotation + degrees) % 360;
    // Clear crop data when rotating since coordinates become invalid
    registerUploadedPhotos[index].cropData = null;
    drawRotatedImage(index);
}

// Remove uploaded photo
function removeUploadPhoto(index) {
    registerUploadedPhotos.splice(index, 1);
    renderUploadedPhotos();
}

// Cropping functionality
let currentCropPhotoIndex = null;
let cropBox = null;
let cropBoxData = { x: 0, y: 0, width: 200, height: 200 };
let isDraggingCrop = false;
let isResizingCrop = false;
let resizeHandle = null;
let dragStartX = 0;
let dragStartY = 0;
let originalCropData = {};

function openCropModal(index) {
    currentCropPhotoIndex = index;
    const photo = registerUploadedPhotos[index];

    // Load image onto crop source canvas
    const canvas = document.getElementById('crop-source-canvas');
    const ctx = canvas.getContext('2d');
    const img = new Image();

    img.onload = () => {
        // Set canvas size to image size (with rotation applied)
        const rotation = photo.rotation || 0;
        const isRotated90 = Math.abs(rotation % 180) === 90;

        if (isRotated90) {
            canvas.width = img.height;
            canvas.height = img.width;
        } else {
            canvas.width = img.width;
            canvas.height = img.height;
        }

        // Draw rotated image
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.save();
        ctx.translate(canvas.width / 2, canvas.height / 2);
        ctx.rotate(rotation * Math.PI / 180);
        ctx.drawImage(img, -img.width / 2, -img.height / 2);
        ctx.restore();

        // Initialize crop box
        if (photo.cropData) {
            // Use existing crop data
            cropBoxData = { ...photo.cropData };
        } else {
            // Default to center 80% of image
            const margin = 0.1;
            cropBoxData = {
                x: canvas.width * margin,
                y: canvas.height * margin,
                width: canvas.width * 0.8,
                height: canvas.height * 0.8
            };
        }

        updateCropBox();
        updateCropPreview();

        // Open modal
        openModal('crop-photo-modal');

        // Setup drag handlers
        setupCropDragHandlers();
    };

    img.src = photo.dataUrl;
}

function setupCropDragHandlers() {
    cropBox = document.getElementById('crop-box');
    const handles = cropBox.querySelectorAll('.crop-handle');

    // Crop box drag
    cropBox.addEventListener('mousedown', startDragCropBox);

    // Handle resize
    handles.forEach(handle => {
        handle.addEventListener('mousedown', (e) => {
            e.stopPropagation();
            startResizeCropBox(e);
        });
    });

    // Global mouse handlers
    document.addEventListener('mousemove', onCropMouseMove);
    document.addEventListener('mouseup', stopCropDrag);
}

function startDragCropBox(e) {
    if (e.target.classList.contains('crop-handle')) return;

    isDraggingCrop = true;
    dragStartX = e.clientX;
    dragStartY = e.clientY;
    originalCropData = { ...cropBoxData };
    e.preventDefault();
}

function startResizeCropBox(e) {
    isResizingCrop = true;
    resizeHandle = e.target.dataset.handle;
    dragStartX = e.clientX;
    dragStartY = e.clientY;
    originalCropData = { ...cropBoxData };
    e.preventDefault();
}

function onCropMouseMove(e) {
    if (!isDraggingCrop && !isResizingCrop) return;

    const canvas = document.getElementById('crop-source-canvas');
    const rect = canvas.getBoundingClientRect();
    const scale = canvas.width / rect.width;

    const deltaX = (e.clientX - dragStartX) * scale;
    const deltaY = (e.clientY - dragStartY) * scale;

    if (isDraggingCrop) {
        // Move crop box
        cropBoxData.x = Math.max(0, Math.min(canvas.width - cropBoxData.width, originalCropData.x + deltaX));
        cropBoxData.y = Math.max(0, Math.min(canvas.height - cropBoxData.height, originalCropData.y + deltaY));
    } else if (isResizingCrop) {
        // Resize crop box based on handle
        switch (resizeHandle) {
            case 'nw':
                cropBoxData.x = Math.max(0, originalCropData.x + deltaX);
                cropBoxData.y = Math.max(0, originalCropData.y + deltaY);
                cropBoxData.width = originalCropData.width - deltaX;
                cropBoxData.height = originalCropData.height - deltaY;
                break;
            case 'ne':
                cropBoxData.y = Math.max(0, originalCropData.y + deltaY);
                cropBoxData.width = originalCropData.width + deltaX;
                cropBoxData.height = originalCropData.height - deltaY;
                break;
            case 'sw':
                cropBoxData.x = Math.max(0, originalCropData.x + deltaX);
                cropBoxData.width = originalCropData.width - deltaX;
                cropBoxData.height = originalCropData.height + deltaY;
                break;
            case 'se':
                cropBoxData.width = originalCropData.width + deltaX;
                cropBoxData.height = originalCropData.height + deltaY;
                break;
        }

        // Ensure minimum size
        cropBoxData.width = Math.max(50, cropBoxData.width);
        cropBoxData.height = Math.max(50, cropBoxData.height);

        // Ensure within canvas bounds
        if (cropBoxData.x + cropBoxData.width > canvas.width) {
            cropBoxData.width = canvas.width - cropBoxData.x;
        }
        if (cropBoxData.y + cropBoxData.height > canvas.height) {
            cropBoxData.height = canvas.height - cropBoxData.y;
        }
    }

    updateCropBox();
    updateCropPreview();
}

function stopCropDrag() {
    isDraggingCrop = false;
    isResizingCrop = false;
    resizeHandle = null;
}

function updateCropBox() {
    const canvas = document.getElementById('crop-source-canvas');
    const rect = canvas.getBoundingClientRect();
    const scale = rect.width / canvas.width;

    cropBox.style.left = (cropBoxData.x * scale) + 'px';
    cropBox.style.top = (cropBoxData.y * scale) + 'px';
    cropBox.style.width = (cropBoxData.width * scale) + 'px';
    cropBox.style.height = (cropBoxData.height * scale) + 'px';
}

function updateCropPreview() {
    const sourceCanvas = document.getElementById('crop-source-canvas');
    const previewCanvas = document.getElementById('crop-preview-canvas');
    const ctx = previewCanvas.getContext('2d');

    // Set preview canvas size
    previewCanvas.width = cropBoxData.width;
    previewCanvas.height = cropBoxData.height;

    // Draw cropped region
    ctx.drawImage(
        sourceCanvas,
        cropBoxData.x, cropBoxData.y, cropBoxData.width, cropBoxData.height,
        0, 0, cropBoxData.width, cropBoxData.height
    );
}

function applyCrop() {
    if (currentCropPhotoIndex !== null) {
        // Save crop data to photo
        registerUploadedPhotos[currentCropPhotoIndex].cropData = { ...cropBoxData };

        // Re-render to show cropped version
        renderUploadedPhotos();
    }

    closeCropModal();
}

function closeCropModal() {
    // Clean up event listeners
    document.removeEventListener('mousemove', onCropMouseMove);
    document.removeEventListener('mouseup', stopCropDrag);

    cropBox = null;
    currentCropPhotoIndex = null;
    isDraggingCrop = false;
    isResizingCrop = false;

    closeModal('crop-photo-modal');
}

async function startRegisterCamera() {
    try {
        registerCameraStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'user', width: 640, height: 480 }
        });
        const camera = document.getElementById('register-camera');
        camera.srcObject = registerCameraStream;
        await camera.play();
    } catch (error) {
        console.error('[REGISTER] Error starting camera:', error);
        showRegisterAlert('Unable to access camera. Please check permissions.', 'error');
    }
}

function stopRegisterCamera() {
    if (registerCameraStream) {
        registerCameraStream.getTracks().forEach(track => track.stop());
        registerCameraStream = null;
    }
}

function showRegisterAlert(message, type = 'info') {
    // Show alert in both camera and upload containers
    const containers = ['register-alert-container', 'upload-alert-container'];
    const alertClass = type === 'error' ? 'alert-error' : type === 'success' ? 'alert-success' : 'alert-info';

    containers.forEach(containerId => {
        const container = document.getElementById(containerId);
        if (container) {
            container.innerHTML = `<div class="alert ${alertClass}" style="margin-bottom: 15px;">${message}</div>`;
            setTimeout(() => {
                container.innerHTML = '';
            }, 3000);
        }
    });
}

document.getElementById('register-begin-btn').addEventListener('click', async () => {
    document.getElementById('register-begin-btn').disabled = true;
    await startRegisterCapture();
});

async function startRegisterCapture() {
    registerCapturedPhotos = [];
    registerCurrentPositionIndex = 0;
    registerCapturing = true;

    await captureNextRegisterPhoto();
}

async function captureNextRegisterPhoto() {
    if (registerCurrentPositionIndex >= registerPositions.length) {
        finishRegisterCapture();
        return;
    }

    const position = registerPositions[registerCurrentPositionIndex];
    const guidanceIndicator = document.getElementById('register-guidance-indicator');

    // Show instruction
    guidanceIndicator.textContent = position.instruction;
    speak(position.instruction);

    // Wait 2 seconds then capture
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Capture photo
    const photoData = captureRegisterPhoto();
    registerCapturedPhotos.push({
        position: position.name,
        image: photoData
    });

    // Update progress
    registerCurrentPositionIndex++;
    document.getElementById('register-photo-count').textContent = registerCurrentPositionIndex;
    document.getElementById('register-progress-fill').style.width = `${(registerCurrentPositionIndex / registerPositions.length) * 100}%`;

    // Next photo
    await new Promise(resolve => setTimeout(resolve, 500));
    await captureNextRegisterPhoto();
}

function captureRegisterPhoto() {
    const camera = document.getElementById('register-camera');
    const canvas = document.getElementById('register-canvas');
    canvas.width = camera.videoWidth;
    canvas.height = camera.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(camera, 0, 0);
    return canvas.toDataURL('image/jpeg', 0.9);
}

function finishRegisterCapture() {
    registerCapturing = false;
    document.getElementById('register-guidance-indicator').textContent = '✓ Complete';
    document.getElementById('register-submit-btn').disabled = false;
    speak('Capture complete. Please press submit.');
}

document.getElementById('register-submit-btn').addEventListener('click', async () => {
    document.getElementById('register-submit-btn').disabled = true;
    await submitRegisterRegistration();
});

// Handle upload submit
document.getElementById('upload-submit-btn').addEventListener('click', async () => {
    document.getElementById('upload-submit-btn').disabled = true;
    await submitUploadRegistration();
});

async function submitUploadRegistration() {
    try {
        showRegisterAlert('Processing and uploading photos...', 'info');

        // Convert canvases to data URLs (includes rotation)
        const photos = [];
        for (let i = 0; i < registerUploadedPhotos.length; i++) {
            const canvas = document.getElementById(`upload-canvas-${i}`);
            if (canvas) {
                const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
                photos.push(dataUrl);
            }
        }

        if (photos.length === 0) {
            showRegisterAlert('No photos to upload', 'error');
            document.getElementById('upload-submit-btn').disabled = false;
            return;
        }

        const response = await fetch('/api/admin/register-face', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                person_name: registerPersonName,
                location_id: registerLocationId,
                photos: photos
            })
        });

        if (response.ok) {
            document.getElementById('register-success-name').textContent = registerPersonName;
            document.querySelectorAll('.register-step').forEach(step => step.classList.remove('active'));
            document.getElementById('register-step-success').classList.add('active');

            // Reload faces list
            await loadRegisteredFaces();
        } else {
            const error = await response.json();
            showRegisterAlert(error.detail || 'Registration failed', 'error');
            document.getElementById('upload-submit-btn').disabled = false;
        }
    } catch (error) {
        console.error('Error:', error);
        showRegisterAlert('Error submitting registration', 'error');
        document.getElementById('upload-submit-btn').disabled = false;
    }
}

async function submitRegisterRegistration() {
    try {
        showRegisterAlert('Submitting registration...', 'info');

        const response = await fetch('/api/admin/register-face', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                person_name: registerPersonName,
                location_id: registerLocationId,
                photos: registerCapturedPhotos
            })
        });

        if (response.ok) {
            stopRegisterCamera();
            document.getElementById('register-success-name').textContent = registerPersonName;
            document.querySelectorAll('.register-step').forEach(step => step.classList.remove('active'));
            document.getElementById('register-step-success').classList.add('active');

            // Reload faces list
            await loadRegisteredFaces();
        } else {
            const error = await response.json();
            showRegisterAlert(error.detail || 'Registration failed', 'error');
            document.getElementById('register-submit-btn').disabled = false;
        }
    } catch (error) {
        console.error('Error:', error);
        showRegisterAlert('Error submitting registration', 'error');
        document.getElementById('register-submit-btn').disabled = false;
    }
}

function speak(text) {
    if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 0.9;
        utterance.pitch = 1;
        speechSynthesis.speak(utterance);
    }
}

// ============================================================================
// CATEGORY & TAG MANAGEMENT
// ============================================================================

let allCategories = [];
let categoryTagsMap = {}; // Map of category_id -> tags array

// Load categories and their tags
async function loadCategories() {
    try {
        const url = managedLocationFilter
            ? `/api/categories?location_id=${managedLocationFilter}`
            : '/api/categories';

        const response = await fetch(url, { credentials: 'include' });
        const data = await response.json();

        if (!data.success) {
            throw new Error('Failed to load categories');
        }

        allCategories = data.categories;

        // Load tags for each category
        for (const category of allCategories) {
            await loadTagsForCategory(category.id);
        }

        displayCategories();
    } catch (error) {
        console.error('Error loading categories:', error);
        showAlert('Failed to load categories', 'error');
    }
}

// Load tags for a specific category
async function loadTagsForCategory(categoryId) {
    try {
        const response = await fetch(`/api/categories/${categoryId}/tags`, {
            credentials: 'include'
        });
        const data = await response.json();

        if (data.success) {
            categoryTagsMap[categoryId] = data.tags;
        }
    } catch (error) {
        console.error(`Error loading tags for category ${categoryId}:`, error);
    }
}

// Display categories with their tags
function displayCategories() {
    const container = document.getElementById('categories-container');

    if (allCategories.length === 0) {
        container.innerHTML = '<div class="empty-state"><div class="icon">🏷️</div><p>No categories yet</p></div>';
        return;
    }

    container.innerHTML = allCategories.map(category => {
        const scopeClass = category.scope === 'global' ? 'global' : 'location';
        const tags = categoryTagsMap[category.id] || [];

        return `
            <div class="category-card">
                <div class="category-header">
                    <div class="category-title">
                        <h3>${escapeHtml(category.name)}</h3>
                        <span class="scope-badge ${scopeClass}">${category.scope === 'global' ? '🌍 Global' : '📍 Location'}</span>
                    </div>
                    <div style="display: flex; gap: 10px;">
                        <button class="btn btn-sm btn-primary" onclick="showCreateTagModal(${category.id}, '${escapeHtml(category.name)}')">+ Add Tag</button>
                        <button class="btn btn-sm btn-secondary" onclick="showEditCategoryModal(${category.id})">Edit</button>
                        <button class="btn btn-sm btn-danger" onclick="deleteCategory(${category.id}, '${escapeHtml(category.name)}')">Delete</button>
                    </div>
                </div>
                ${category.description ? `<p style="color: #666; margin-bottom: 10px;">${escapeHtml(category.description)}</p>` : ''}
                <div class="tags-grid">
                    ${tags.length === 0 ? '<p style="color: #999; font-style: italic;">No tags yet</p>' : tags.map(tag => `
                        <div class="tag-item">
                            <span>${escapeHtml(tag.name)}</span>
                            <button onclick="showEditTagModal(${tag.id}, ${category.id})" title="Edit">✏️</button>
                            <button onclick="deleteTag(${tag.id}, ${category.id}, '${escapeHtml(tag.name)}')" title="Delete">×</button>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }).join('');
}

// Show create category modal
async function showCreateCategoryModal() {
    document.getElementById('create-category-form').reset();
    document.getElementById('category-location-group').style.display = 'none';

    // Load locations if not already loaded
    if (allLocations.length === 0) {
        await loadLocations();
    }

    // Populate locations
    const locationSelect = document.getElementById('category-location');
    locationSelect.innerHTML = '<option value="">Select location...</option>';
    allLocations.forEach(loc => {
        const option = document.createElement('option');
        option.value = loc.id;
        option.textContent = loc.name;
        locationSelect.appendChild(option);
    });

    openModal('create-category-modal');
}

// Toggle category location dropdown based on scope
function toggleCategoryLocation() {
    const scope = document.getElementById('category-scope').value;
    const locationGroup = document.getElementById('category-location-group');
    const locationSelect = document.getElementById('category-location');

    if (scope === 'location') {
        locationGroup.style.display = 'block';
        locationSelect.setAttribute('required', 'required');
    } else {
        locationGroup.style.display = 'none';
        locationSelect.removeAttribute('required');
        locationSelect.value = ''; // Clear selection when hiding
    }
}

// Create category form submission
document.getElementById('create-category-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const scope = document.getElementById('category-scope').value;
    const locationValue = document.getElementById('category-location').value;

    // Validate location selection for location-specific categories
    if (scope === 'location' && (!locationValue || locationValue === '')) {
        showAlert('Please select a location for location-specific categories', 'error');
        return;
    }

    const data = {
        name: document.getElementById('category-name').value,
        description: document.getElementById('category-description').value || null,
        scope: scope,
        location_id: scope === 'location' ? parseInt(locationValue) : null
    };

    try {
        const response = await fetch('/api/categories', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showAlert('Category created successfully', 'success');
            closeModal('create-category-modal');
            await loadCategories();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to create category', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error creating category', 'error');
    }
});

// Show edit category modal
async function showEditCategoryModal(categoryId) {
    const category = allCategories.find(c => c.id === categoryId);
    if (!category) return;

    document.getElementById('edit-category-id').value = category.id;
    document.getElementById('edit-category-name').value = category.name;
    document.getElementById('edit-category-description').value = category.description || '';

    openModal('edit-category-modal');
}

// Edit category form submission
document.getElementById('edit-category-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const categoryId = document.getElementById('edit-category-id').value;
    const data = {
        name: document.getElementById('edit-category-name').value,
        description: document.getElementById('edit-category-description').value || null
    };

    try {
        const response = await fetch(`/api/categories/${categoryId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showAlert('Category updated successfully', 'success');
            closeModal('edit-category-modal');
            await loadCategories();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to update category', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error updating category', 'error');
    }
});

// Delete category
async function deleteCategory(categoryId, categoryName) {
    if (!confirm(`Delete category "${categoryName}" and all its tags?\n\nThis will also remove these tags from all people. This cannot be undone.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/categories/${categoryId}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        if (response.ok) {
            showAlert(`Category "${categoryName}" deleted`, 'success');
            await loadCategories();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to delete category', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error deleting category', 'error');
    }
}

// Show create tag modal
function showCreateTagModal(categoryId, categoryName) {
    document.getElementById('create-tag-form').reset();
    document.getElementById('tag-category-id').value = categoryId;
    document.getElementById('tag-category-name').value = categoryName;
    openModal('create-tag-modal');
}

// Create tag form submission
document.getElementById('create-tag-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const data = {
        category_id: parseInt(document.getElementById('tag-category-id').value),
        name: document.getElementById('tag-name').value,
        description: document.getElementById('tag-description').value || null
    };

    try {
        const response = await fetch('/api/tags', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showAlert('Tag created successfully', 'success');
            closeModal('create-tag-modal');
            await loadCategories();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to create tag', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error creating tag', 'error');
    }
});

// Show edit tag modal
async function showEditTagModal(tagId, categoryId) {
    const tags = categoryTagsMap[categoryId];
    const tag = tags.find(t => t.id === tagId);
    if (!tag) return;

    document.getElementById('edit-tag-id').value = tag.id;
    document.getElementById('edit-tag-name').value = tag.name;
    document.getElementById('edit-tag-description').value = tag.description || '';

    openModal('edit-tag-modal');
}

// Edit tag form submission
document.getElementById('edit-tag-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const tagId = document.getElementById('edit-tag-id').value;
    const data = {
        name: document.getElementById('edit-tag-name').value,
        description: document.getElementById('edit-tag-description').value || null
    };

    try {
        const response = await fetch(`/api/tags/${tagId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showAlert('Tag updated successfully', 'success');
            closeModal('edit-tag-modal');
            await loadCategories();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to update tag', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error updating tag', 'error');
    }
});

// Delete tag
async function deleteTag(tagId, categoryId, tagName) {
    if (!confirm(`Delete tag "${tagName}"?\n\nThis will remove this tag from all people. This cannot be undone.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/tags/${tagId}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        if (response.ok) {
            showAlert(`Tag "${tagName}" deleted`, 'success');
            await loadCategories();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to delete tag', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error deleting tag', 'error');
    }
}

// Show assign tags modal for a person
let currentAssignPersonId = null;
let currentAssignPersonName = null;
let currentAssignLocationId = null;

async function showAssignTagsModal(personId, personName, locationId) {
    currentAssignPersonId = personId;
    currentAssignPersonName = personName;
    currentAssignLocationId = locationId;

    document.getElementById('assign-tags-person-name').textContent = personName;

    // Load categories if not already loaded
    if (allCategories.length === 0) {
        await loadCategories();
    }

    // Load current tags for person
    const personTags = await loadPersonTags(personId, locationId);
    const personTagIds = personTags.map(t => t.tag_id);

    // Build UI with categories and checkboxes
    const container = document.getElementById('assign-tags-container');

    if (allCategories.length === 0) {
        container.innerHTML = '<p style="color: #999; padding: 20px; text-align: center;">No categories available. Please create categories and tags first in the Categories & Tags tab.</p>';
        openModal('assign-tags-modal');
        return;
    }

    container.innerHTML = allCategories.map(category => {
        const tags = categoryTagsMap[category.id] || [];
        if (tags.length === 0) return '';

        return `
            <div class="tag-checkbox-group">
                <h4>${escapeHtml(category.name)} <span class="scope-badge ${category.scope}">${category.scope === 'global' ? '🌍' : '📍'}</span></h4>
                <div class="tag-checkbox-list">
                    ${tags.map(tag => `
                        <label>
                            <input type="checkbox" value="${tag.id}" ${personTagIds.includes(tag.id) ? 'checked' : ''}>
                            ${escapeHtml(tag.name)}
                            ${tag.description ? `<span style="color: #999; font-size: 12px;">- ${escapeHtml(tag.description)}</span>` : ''}
                        </label>
                    `).join('')}
                </div>
            </div>
        `;
    }).join('');

    openModal('assign-tags-modal');
}

// Load current tags for a person
async function loadPersonTags(personId, locationId) {
    try {
        const response = await fetch(`/api/person-tags/${encodeURIComponent(personId)}?location_id=${locationId}`, {
            credentials: 'include'
        });
        const data = await response.json();
        return data.success ? data.tags : [];
    } catch (error) {
        console.error('Error loading person tags:', error);
        return [];
    }
}

// Save person tags
async function savePersonTags() {
    const checkboxes = document.querySelectorAll('#assign-tags-container input[type="checkbox"]:checked');
    const tagIds = Array.from(checkboxes).map(cb => parseInt(cb.value));

    try {
        const response = await fetch('/api/person-tags', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                person_id: currentAssignPersonId,
                person_name: currentAssignPersonName,
                location_id: currentAssignLocationId,
                tag_ids: tagIds
            })
        });

        if (response.ok) {
            showAlert(`Tags updated for ${currentAssignPersonName}`, 'success');
            closeModal('assign-tags-modal');
            await loadRegisteredFaces();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to update tags', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error updating tags', 'error');
    }
}

// ============================================================================
// EDIT PHOTOS / CROPPING
// ============================================================================

let currentEditPhotos = {
    personId: null,
    personName: null,
    photos: [],
    selectedPhotoIndex: null,
    cropper: null,
    croppedImages: []
};

// Wrapper to read data from button and show edit photos modal
function showEditPhotosModalFromButton(button) {
    const personId = button.getAttribute('data-person-id');
    const personName = button.getAttribute('data-person-name');
    const photosJson = button.getAttribute('data-photos');
    showEditPhotosModal(personId, personName, photosJson);
}

// Show edit photos modal
function showEditPhotosModal(personId, personName, photosJson) {
    try {
        // Parse photos (they come as JSON string from the onclick attribute)
        const photos = typeof photosJson === 'string' ? JSON.parse(photosJson) : photosJson;

        currentEditPhotos.personId = personId;
        currentEditPhotos.personName = personName;
        currentEditPhotos.photos = photos;
        currentEditPhotos.selectedPhotoIndex = null;
        currentEditPhotos.croppedImages = [];

        // Update modal title
        document.getElementById('edit-photos-person-name').textContent = personName;

        // Display photos in selection grid
        const photosList = document.getElementById('edit-photos-list');
        photosList.innerHTML = photos.map((photo, index) => `
            <div class="crop-preview-item" onclick="selectPhotoForCrop(${index})">
                <img src="${photo}" alt="Photo ${index + 1}">
                <div style="text-align: center; padding: 5px; font-size: 12px; background: rgba(255,255,255,0.9);">
                    Photo ${index + 1}
                </div>
            </div>
        `).join('');

        // Show selection step
        document.getElementById('edit-photos-step-select').style.display = 'block';
        document.getElementById('edit-photos-step-crop').style.display = 'none';
        document.getElementById('edit-photos-step-saving').style.display = 'none';
        document.getElementById('edit-photos-close-btn').style.display = 'flex';

        // Open modal
        openModal('edit-photos-modal');
    } catch (error) {
        console.error('Error showing edit photos modal:', error);
        showAlert('Error loading photos', 'error');
    }
}

// Select a photo for cropping
function selectPhotoForCrop(photoIndex) {
    currentEditPhotos.selectedPhotoIndex = photoIndex;
    const photoUrl = currentEditPhotos.photos[photoIndex];

    // Hide selection, show crop step
    document.getElementById('edit-photos-step-select').style.display = 'none';
    document.getElementById('edit-photos-step-crop').style.display = 'block';
    document.getElementById('edit-photos-close-btn').style.display = 'none';

    // Set image source
    const image = document.getElementById('crop-target-image');
    image.src = photoUrl;

    // Destroy existing cropper if any
    if (currentEditPhotos.cropper) {
        currentEditPhotos.cropper.destroy();
    }

    // Initialize Cropper.js when image loads
    image.onload = function() {
        currentEditPhotos.cropper = new Cropper(image, {
            aspectRatio: NaN, // Free aspect ratio
            viewMode: 1,
            autoCropArea: 0.8,
            responsive: true,
            background: false,
            ready: function() {
                // Auto-detect face after cropper is ready
                setTimeout(() => autoDetectFace(), 500);
            }
        });
    };
}

// Auto-detect face and set crop area
async function autoDetectFace() {
    if (!currentEditPhotos.cropper) return;

    try {
        const photoUrl = currentEditPhotos.photos[currentEditPhotos.selectedPhotoIndex];

        // Show loading indicator
        showAlert('Detecting face...', 'info');

        // Call CodeProject.AI face detection
        const response = await fetch(photoUrl);
        const blob = await response.blob();

        const formData = new FormData();
        formData.append('image', blob, 'photo.jpg');

        // Get CodeProject endpoint from first server (we'll use the person's registered server)
        const detectResponse = await fetch('/api/detect-face-bounds', {
            method: 'POST',
            credentials: 'include',
            body: formData
        });

        if (detectResponse.ok) {
            const data = await detectResponse.json();
            if (data.success && data.faces && data.faces.length > 0) {
                const face = data.faces[0]; // Use first detected face

                // Add padding around the face to include whole head
                const faceWidth = face.x_max - face.x_min;
                const faceHeight = face.y_max - face.y_min;

                // Add padding to capture whole head (more horizontal for ears, less vertical to avoid too much background)
                const paddingX = faceWidth * 0.4;  // 40% horizontal padding for ears
                const paddingY = faceHeight * 0.3; // 30% vertical padding for hair/neck

                // Get image dimensions to ensure we don't go out of bounds
                const imageData = currentEditPhotos.cropper.getImageData();

                const x = Math.max(0, face.x_min - paddingX);
                const y = Math.max(0, face.y_min - paddingY);
                const width = Math.min(imageData.naturalWidth - x, faceWidth + (paddingX * 2));
                const height = Math.min(imageData.naturalHeight - y, faceHeight + (paddingY * 2));

                currentEditPhotos.cropper.setData({
                    x: x,
                    y: y,
                    width: width,
                    height: height
                });

                showAlert('Face detected and cropped!', 'success');
            } else {
                showAlert('No face detected. Please crop manually.', 'warning');
            }
        } else {
            showAlert('Face detection unavailable. Please crop manually.', 'warning');
        }
    } catch (error) {
        console.error('Error detecting face:', error);
        showAlert('Face detection error. Please crop manually.', 'warning');
    }
}

// Reset crop to original
function resetCrop() {
    if (currentEditPhotos.cropper) {
        currentEditPhotos.cropper.reset();
    }
}

// Back to photo selection
function backToPhotoSelection() {
    // Destroy cropper
    if (currentEditPhotos.cropper) {
        currentEditPhotos.cropper.destroy();
        currentEditPhotos.cropper = null;
    }

    // Show selection step
    document.getElementById('edit-photos-step-select').style.display = 'block';
    document.getElementById('edit-photos-step-crop').style.display = 'none';
    document.getElementById('edit-photos-close-btn').style.display = 'flex';
}

// Apply cropped photo and save
async function applyCroppedPhoto() {
    if (!currentEditPhotos.cropper) return;

    try {
        // Show saving step
        document.getElementById('edit-photos-step-crop').style.display = 'none';
        document.getElementById('edit-photos-step-saving').style.display = 'block';

        // Get cropped canvas
        const canvas = currentEditPhotos.cropper.getCroppedCanvas({
            maxWidth: 4096,
            maxHeight: 4096,
            imageSmoothingEnabled: true,
            imageSmoothingQuality: 'high'
        });

        // Convert to blob
        const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.95));

        // Create FormData with all photos
        const formData = new FormData();
        formData.append('person_id', currentEditPhotos.personId);
        formData.append('person_name', currentEditPhotos.personName);

        // Add all photos (with cropped photo in the correct position)
        for (let i = 0; i < currentEditPhotos.photos.length; i++) {
            if (i === currentEditPhotos.selectedPhotoIndex) {
                // Add cropped version
                formData.append('photos', blob, `photo_${i}.jpg`);
            } else {
                // Fetch and add original photos
                const photoResponse = await fetch(currentEditPhotos.photos[i]);
                const photoBlob = await photoResponse.blob();
                formData.append('photos', photoBlob, `photo_${i}.jpg`);
            }
        }

        // Call backend to replace photos
        const response = await fetch('/api/admin/replace-photos', {
            method: 'POST',
            credentials: 'include',
            body: formData
        });

        if (response.ok) {
            showAlert('Photos updated successfully!', 'success');

            // Reload the registered faces data in the background
            await loadRegisteredFaces();

            // Fetch updated photos for this person
            const facesResponse = await fetch('/api/registered-faces', {
                credentials: 'include'
            });
            const facesData = await facesResponse.json();
            const updatedPerson = facesData.faces.find(f => f.person_id === currentEditPhotos.personId);

            if (updatedPerson && updatedPerson.all_photos) {
                // Update the photos array with the new photos
                currentEditPhotos.photos = updatedPerson.all_photos;

                // Refresh the photo selection list
                const photosList = document.getElementById('edit-photos-list');
                photosList.innerHTML = currentEditPhotos.photos.map((photo, index) => `
                    <div class="crop-preview-item" onclick="selectPhotoForCrop(${index})">
                        <img src="${photo}" alt="Photo ${index + 1}">
                        <div style="text-align: center; padding: 5px; font-size: 12px; background: rgba(255,255,255,0.9);">
                            Photo ${index + 1}
                        </div>
                    </div>
                `).join('');
            }

            // Go back to photo selection so user can crop another photo or close
            backToPhotoSelection();
        } else {
            const error = await response.json();
            showAlert(error.detail || 'Failed to update photos', 'error');
            backToPhotoSelection();
        }
    } catch (error) {
        console.error('Error applying crop:', error);
        showAlert('Error saving cropped photo', 'error');
        backToPhotoSelection();
    }
}

// Close edit photos modal
function closeEditPhotosModal() {
    // Destroy cropper
    if (currentEditPhotos.cropper) {
        currentEditPhotos.cropper.destroy();
        currentEditPhotos.cropper = null;
    }

    // Reset state
    currentEditPhotos = {
        personId: null,
        personName: null,
        photos: [],
        selectedPhotoIndex: null,
        cropper: null,
        croppedImages: []
    };

    // Close modal
    closeModal('edit-photos-modal');
}

// Initialize on page load
init();
