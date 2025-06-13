document.addEventListener('DOMContentLoaded', () => {
    // Login functionality remains unchanged.
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            const response = await fetch('/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = await response.json();
            if (data.status === 'OK') window.location.href = '/chat';
            else alert(data.message);
        });
    }

    // Chat page functionality.
    const sendForm = document.getElementById('send-form');
    if (sendForm) {
        const username = (window.chatData && window.chatData.username) || '';
        const rawRecipient = (window.chatData && window.chatData.recipient)
            ? window.chatData.recipient
            : window.location.pathname.split('/').pop();
        const recipient = rawRecipient.replace(/\?+\s*$/, '');
        const room = [username, recipient].sort().join('_');
        
        const historyContainer = document.getElementById('chat-container');
        const messageInput = document.getElementById('message');
        const socket = io();

        let pendingMessageIDs = [];
        let pendingCounter = 1;
        let renderedDateHeaders = new Set(); // Track rendered date headers

        // Helper function to format timestamp to local time
        function formatTimestamp(timestamp) {
            const date = new Date(timestamp * 1000); // Convert Unix timestamp to milliseconds
            return {
                date: date.toISOString().split('T')[0], // YYYY-MM-DD format without timezone affecting it
                time: date.toLocaleTimeString('en-US', { 
                    hour: '2-digit', 
                    minute: '2-digit', 
                    hour12: false 
                })
            };
        }

        // Helper function to get date header for a given date string
        function getDateHeader(dateString) {
            // Ensure we properly parse the date string as local date
            const messageDate = new Date(dateString + 'T00:00:00');
            
            // Get today/yesterday dates at midnight for proper comparison
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            
            const yesterday = new Date(today);
            yesterday.setDate(yesterday.getDate() - 1);
            
            const oneWeekAgo = new Date(today);
            oneWeekAgo.setDate(oneWeekAgo.getDate() - 7);

            // Compare dates at midnight level for accurate day comparison
            if (messageDate.getTime() === today.getTime()) {
                return "Today";
            } else if (messageDate.getTime() === yesterday.getTime()) {
                return "Yesterday";
            } else if (messageDate >= oneWeekAgo) {
                return messageDate.toLocaleDateString('en-US', { weekday: 'long' });
            } else {
                return messageDate.toLocaleDateString('en-US', { month: 'long', day: 'numeric' });
            }
        }

        // Helper function to add date header if needed
        function addDateHeaderIfNeeded(dateString) {
            const dateHeader = getDateHeader(dateString);
            if (!renderedDateHeaders.has(dateHeader)) {
                const headerHtml = `
                    <div class="text-center my-4" data-date-header="${dateHeader}">
                        <span class="bg-gray-200 text-gray-600 px-3 py-1 rounded-full text-sm font-medium">
                            ${dateHeader}
                        </span>
                    </div>`;
                historyContainer.insertAdjacentHTML('beforeend', headerHtml);
                renderedDateHeaders.add(dateHeader);
            }
        }

        // Function to render a single message
        function renderMessage(msg, isFromCurrentUser) {
            const formatted = formatTimestamp(msg.timestamp);
            addDateHeaderIfNeeded(formatted.date);

            const alignment = isFromCurrentUser ? 'text-right' : 'text-left';
            const bgColor = isFromCurrentUser ? 'bg-blue-500 text-white' : 'bg-gray-300 text-gray-800';
            
            return `
                <div class="${alignment} mb-2">
                    <span class="${bgColor} rounded px-3 py-1 inline-block">
                        ${msg.message}
                    </span>
                    <span class="text-xs text-gray-500">${formatted.time}</span>
                </div>`;
        }

        // Function to initialize chat with existing messages
        function initializeChat() {
            const loadingElement = document.getElementById('loading');
            if (loadingElement) loadingElement.remove();

            if (window.chatData && window.chatData.initialConversation) {
                const conversation = [...window.chatData.initialConversation]; // Clone the array
                
                // Sort messages by timestamp (oldest first)
                conversation.sort((a, b) => a.timestamp - b.timestamp);
                
                // Clear existing rendered headers
                renderedDateHeaders.clear();
                historyContainer.innerHTML = '';
                
                for (const msg of conversation) {
                    const isFromCurrentUser = msg.sender === username;
                    historyContainer.insertAdjacentHTML('beforeend', 
                        renderMessage(msg, isFromCurrentUser));
                }
                historyContainer.scrollTop = historyContainer.scrollHeight;
            }
        }

        // When the socket connects, join the conversation room.
        socket.on('connect', () => {
            socket.emit('join', { room: room });
            initializeChat();
        });

        // Listen for new message events.
        socket.on('new_message', (data) => {
            console.log('Received message:', data);
            
            const formatted = formatTimestamp(data.timestamp);
            
            // If the message is from the current user, try to replace a pending message.
            if (data.sender === username) {
                if (pendingMessageIDs.length > 0) {
                    const pendingID = pendingMessageIDs[0];
                    const pendingElem = document.getElementById(pendingID);
                    if (pendingElem) {
                        // Check if we need a date header before the message
                        addDateHeaderIfNeeded(formatted.date);
                        
                        const newMsgHtml = `
                            <div class="text-right mb-2">
                                <span class="bg-blue-500 text-white rounded px-3 py-1 inline-block">
                                    ${data.message}
                                </span>
                                <span class="text-xs text-gray-500">${formatted.time}</span>
                            </div>`;
                        pendingElem.outerHTML = newMsgHtml;
                        pendingMessageIDs.shift();
                        historyContainer.scrollTop = historyContainer.scrollHeight;
                        return;
                    }
                }
                
                // If no pending element was found, append normally
                addDateHeaderIfNeeded(formatted.date);
                const newMsgHtml = `
                    <div class="text-right mb-2">
                        <span class="bg-blue-500 text-white rounded px-3 py-1 inline-block">
                            ${data.message}
                        </span>
                        <span class="text-xs text-gray-500">${formatted.time}</span>
                    </div>`;
                historyContainer.insertAdjacentHTML('beforeend', newMsgHtml);
            } else {
                // For messages sent by the other user, simply append them.
                addDateHeaderIfNeeded(formatted.date);
                const newMsgHtml = `
                    <div class="text-left mb-2">
                        <span class="bg-gray-300 text-gray-800 rounded px-3 py-1 inline-block">
                            ${data.message}
                        </span>
                        <span class="text-xs text-gray-500">${formatted.time}</span>
                    </div>`;
                historyContainer.insertAdjacentHTML('beforeend', newMsgHtml);
            }
            historyContainer.scrollTop = historyContainer.scrollHeight;
        });

        // Listen for user status changes
        socket.on('user_status_change', (data) => {
            if (data.username === recipient) {
                const statusText = document.getElementById('status-text');
                const statusIndicator = document.getElementById('status-indicator');
                
                if (data.status === 'online') {
                    statusText.textContent = 'Online';
                    statusText.classList.remove('text-gray-500');
                    statusText.classList.add('text-gray-400');
                    statusIndicator.classList.remove('bg-red-400');
                    statusIndicator.classList.add('bg-green-400');
                } else {
                    statusText.textContent = 'Offline';
                    statusText.classList.remove('text-gray-400');
                    statusText.classList.add('text-gray-500');
                    statusIndicator.classList.remove('bg-green-400');
                    statusIndicator.classList.add('bg-red-400');
                }
            }
        });

        // When the user sends a message.
        sendForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const message = messageInput.value.trim();
            if (message === '') return;

            const pendingID = "pending_" + pendingCounter;
            pendingCounter++;
            pendingMessageIDs.push(pendingID);

            // Add date header for today if needed (for the first message of the day)
            const today = new Date();
            const todayString = today.toISOString().split('T')[0];
            addDateHeaderIfNeeded(todayString);

            const pendingHtml = `
                <div id="${pendingID}" class="text-right mb-2">
                    <span class="bg-blue-500 text-white rounded px-3 py-1 inline-block">
                        ${message} <span class="inline-block animate-spin">⏳</span>
                    </span>
                </div>`;
            historyContainer.insertAdjacentHTML('beforeend', pendingHtml);
            historyContainer.scrollTop = historyContainer.scrollHeight;

            await fetch('/send_message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ recipient, message })
            });
            messageInput.value = '';
        });
    }
});