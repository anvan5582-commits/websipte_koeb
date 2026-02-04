document.addEventListener('DOMContentLoaded', () => {
    if (!document.body) {
        return;
    }
    const baseUrl = `https://htmlsync.io`;

    // Extract tool name from subdomain for API calls
    const getUsername = () => {
        const hostname = window.location.hostname;
        const parts = hostname.split('.');
        const username = parts[0].split('-')[1];
        return username;
    };

    // Extract tool name from subdomain for API calls
    const getToolName = () => {
        const hostname = window.location.hostname;
        const parts = hostname.split('.');
        const appSlug = parts[0].split('-')[0];
        return appSlug;
    };

    const appSlug = getToolName();
    if (!appSlug) {
        return; // Not a tool subdomain
    }

    const username = getUsername();
    if (!username) {
        return; // Not a tool subdomain
    }

    // Check if notification was dismissed within the last hour
    const checkDismissal = (key) => {
        const dismissedTime = localStorage.getItem(key);
        const oneHourInMs = 60 * 60 * 1000; // 1 hour in milliseconds
        return dismissedTime && (Date.now() - parseInt(dismissedTime)) < oneHourInMs;
    };

    // Check if any notification is already shown
    if (document.querySelector('.ss-sync-banner, .ss-sync-notification')) {
        return;
    }

    // Check if notification was dismissed
    const notificationDismissedKey = 'ss-sync-notification-dismissed';
    if (checkDismissal(notificationDismissedKey)) {
        return;
    }

    // Check if banner was dismissed (for unauthenticated users)
    const bannerDismissedKey = 'ss-sync-banner-dismissed';
    if (checkDismissal(bannerDismissedKey)) {
        return;
    }

    // Add styles for notifications
    const style = document.createElement('style');
    style.textContent = `
        .ss-sync-banner {
            display: flex;
            gap: 10px;
            justify-content: center;
            align-items: center;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            padding: 12px 20px;
            background: #33658A;
            color: #fff;
            font-size: 16px;
            font-family: Arial, sans-serif;
            z-index: 1000000;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .ss-sync-notification {
            display: flex;
            gap: 10px;
            justify-content: center;
            align-items: center;
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            background: #33658A;
            color: #fff;
            font-size: 14px;
            font-family: Arial, sans-serif;
            z-index: 1000000;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            border-radius: 8px;
            max-width: 400px;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }

        .ss-sync-notification:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(0,0,0,0.2);
        }

        .ss-sync-notification.success {
            background: #10B981;
        }

        .ss-sync-notification.warning {
            background: #F59E0B;
        }

        .ss-sync-notification-content {
            display: flex;
            align-items: center;
            gap: 10px;
            cursor: pointer;
            flex: 1;
        }

        .ss-sync-notification-text {
            display: flex;
            flex-direction: column;
            gap: 2px;
            flex: 1;
        }

        .ss-sync-notification-header {
            font-weight: bold;
            font-size: 14px;
            line-height: 1.2;
        }

        .ss-sync-notification-body {
            font-size: 13px;
            line-height: 1.3;
            opacity: 0.9;
        }

        .ss-sync-notification-close {
            background: none;
            border: none;
            color: #fff;
            font-size: 18px;
            cursor: pointer;
            padding: 0;
            width: 20px;
            height: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            transition: background-color 0.2s;
            flex-shrink: 0;
        }

        .ss-sync-notification-close:hover {
            background-color: rgba(255,255,255,0.2);
        }

        .ss-sync-banner-content {
            display: flex;
            align-items: center;
            gap: 10px;
            cursor: pointer;
            flex: 1;
            justify-content: center;
        }

        .ss-sync-banner-close {
            background: none;
            border: none;
            color: #fff;
            font-size: 20px;
            cursor: pointer;
            padding: 0;
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            transition: background-color 0.2s;
        }

        .ss-sync-banner-close:hover {
            background-color: rgba(255,255,255,0.2);
        }



        .ss-sync-notification .icon {
            width: 16px;
            height: 16px;
            flex-shrink: 0;
        }


    `;
    document.head.appendChild(style);

    // Function to collect all localStorage data
    const collectLocalStorageData = () => {
        const data = {};
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key && !key.startsWith('ss-sync-')) { // Exclude our own keys
                data[key] = localStorage.getItem(key);
            }
        }
        return data;
    };

    /**
     * Get the CSRF token from the cookie
     * @private
     */
    const getCsrfToken = () => {
        // Get the CSRF token from the cookie
        const csrfCookie = document.cookie.match(/XSRF-TOKEN=([^;]+)/);
        if (!csrfCookie) {
            console.warn('CSRF token cookie not found');
            return '';
        }
        const token = decodeURIComponent(csrfCookie[1]);
        return token;
    };

    // Function to sync data to existing program
    const syncToExistingProgram = async (programId, localStorageData) => {
        try {
            const url = `/api/sync-storage/${programId}`;

            const headers = {
                'Content-Type': 'application/json',
                'X-XSRF-TOKEN': getCsrfToken(),
            };

            const body = JSON.stringify({ localStorage_data: localStorageData });

            const response = await fetch(url, {
                method: 'POST',
                headers: headers,
                body: body,
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error('Failed to sync data');
            }

            const result = await response.json();
            return result.program_url;
        } catch (error) {
            console.error('Error syncing data:', error);
            throw error;
        }
    };

    // Function to create program and sync data
    const createProgramAndSync = async (templateSlug, localStorageData) => {
        try {
            const url = `/api/create-from-template-and-sync`;
            const headers = {
                'Content-Type': 'application/json',
                'X-XSRF-TOKEN': getCsrfToken(),
            };

            const body = JSON.stringify({
                template_slug: templateSlug,
                localStorage_data: localStorageData,
                username: username
            });

            const response = await fetch(url, {
                method: 'POST',
                headers: headers,
                body: body,
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error('Failed to create program');
            }

            const result = await response.json();
            return result.program_url;
        } catch (error) {
            console.error('Error creating program:', error);
            throw error;
        }
    };

    // Function to create notification
    const createNotification = (message, type = 'default', onClick, header = null) => {
        const notification = document.createElement('div');
        notification.classList.add('ss-sync-notification');
        if (type !== 'default') {
            notification.classList.add(type);
        }

        const content = document.createElement('div');
        content.classList.add('ss-sync-notification-content');
        content.addEventListener('click', onClick);

        const icon = document.createElement('img');
        icon.src = 'http://htmlsync.io/logo.svg';
        icon.alt = 'HTMLSync';
        icon.width = 16;
        icon.height = 16;
        icon.classList.add('icon');
        content.appendChild(icon);

        // Create text container
        const textContainer = document.createElement('div');
        textContainer.classList.add('ss-sync-notification-text');

        // Add header if provided
        if (header) {
            const headerElement = document.createElement('div');
            headerElement.classList.add('ss-sync-notification-header');
            headerElement.textContent = header;
            textContainer.appendChild(headerElement);
        }

        // Add body text
        const bodyElement = document.createElement('div');
        bodyElement.classList.add(header ? 'ss-sync-notification-body' : 'ss-sync-notification-body');
        bodyElement.textContent = message;
        textContainer.appendChild(bodyElement);

        content.appendChild(textContainer);

        const closeButton = document.createElement('button');
        closeButton.classList.add('ss-sync-notification-close');
        closeButton.innerHTML = '×';
        closeButton.addEventListener('click', (e) => {
            e.stopPropagation();
            localStorage.setItem(notificationDismissedKey, Date.now().toString());
            notification.remove();
        });

        notification.appendChild(content);
        notification.appendChild(closeButton);
        document.body.appendChild(notification);

        return notification;
    };

    // Function to create banner (reusable for both sync and upgrade)
    const createBanner = (message, redirectUrl, dismissKey = bannerDismissedKey) => {
        const banner = document.createElement('div');
        banner.classList.add('ss-sync-banner');

        const content = document.createElement('div');
        content.classList.add('ss-sync-banner-content');
        content.addEventListener('click', () => {
            window.location.href = redirectUrl;
        });

        const icon = document.createElement('img');
        icon.src = 'http://htmlsync.io/logo.svg';
        icon.alt = 'HTMLSync';
        icon.width = 20;
        icon.height = 20;
        content.appendChild(icon);

        const text = document.createElement('span');
        text.innerHTML = message;
        content.appendChild(text);

        const closeButton = document.createElement('button');
        closeButton.classList.add('ss-sync-banner-close');
        closeButton.innerHTML = '×';
        closeButton.addEventListener('click', (e) => {
            e.stopPropagation();
            localStorage.setItem(dismissKey, Date.now().toString());
            banner.remove();
            document.body.style.paddingTop = '0';
        });

        banner.appendChild(content);
        banner.appendChild(closeButton);
        document.body.appendChild(banner);

        // Add padding to body only when banner is created
        document.body.style.paddingTop = '48px';
    };

    // Main logic: Check authentication and program status
    const checkProgramStatus = async () => {
        try {
            const url = `/api/check-program-template/${appSlug}`;

            const headers = {
                'Content-Type': 'application/json',
                'X-XSRF-TOKEN': getCsrfToken(),
            };

            const response = await fetch(url, {
                method: 'GET',
                headers: headers,
            });

            if (response.status === 401) {
                // User is not authenticated - show banner
                const regusterUrl = `${baseUrl}/app/register`;
                const redirectUrl = `${regusterUrl}?utm_source=${encodeURIComponent(appSlug)}`;
                createBanner(`<b><u>Your data is currently <i>ONLY</i> stored in this browser.</u></b> Register to store the data and sync it across all your devices!`, redirectUrl);
                return;
            }

            if (!response.ok) {
                const errorText = await response.text();
                console.error('Error checking app status:', response.status);
                return;
            }

            const data = await response.json();
            const localStorageData = collectLocalStorageData();

            if (data.has_program) {
                // User has a program - show sync notification
                let message, type;

                if (data.has_existing_data) {
                    message = `Sync your data to "${data.program_name}" (existing data will be replaced)`;
                    type = 'warning';
                } else {
                    message = `Sync your data to "${data.program_name}"`;
                    type = 'success';
                }

                createNotification(message, type, async () => {
                    try {
                        const programUrl = await syncToExistingProgram(data.program_id, localStorageData);
                        window.location.href = programUrl;
                    } catch (error) {
                        alert('Failed to sync data. Please try again.');
                    }
                });
            } else {
                // User doesn't have a program - check if they can create one
                if (data.can_create_program) {
                    // User can create a program - show create notification
                    createNotification('Synchronize your data across devices, modify the app to your liking, and share it with anyone!', 'success', async () => {
                        try {
                            const programUrl = await createProgramAndSync(appSlug, localStorageData);
                            window.location.href = programUrl;
                        } catch (error) {
                            alert('Failed to create program. Please try again.');
                        }
                    }, 'Click here to make this app your own!');
                } else {
                    // User cannot create a program - show upgrade banner
                    const pricingUrl = `${baseUrl}/app/billing?utm_source=tool-${encodeURIComponent(appSlug)}`;
                    createBanner(`<u><b>You are out of free apps.</b></u> Upgrade your plan to create more apps and sync your data!`, pricingUrl);
                }
            }
        } catch (error) {
            console.error('Error checking app status:', error);
            // Fallback to banner if there's an error
            const registerUrl = `${baseUrl}/app/register?utm_source=tool-${encodeURIComponent(appSlug)}`;
            createBanner(`<u><b>Your data is currently <i>ONLY</i> stored in this browser.</b></u> Register to store the data and sync it across all your devices!`, registerUrl);
        }
    };

    // Start the check
    checkProgramStatus();
});
