document.addEventListener('DOMContentLoaded', () => {
    // Current timezone
    const LOCAL_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone;

    async function syncTimezoneWithBackend() {
        if (localStorage.getItem('tz_synced') === LOCAL_TZ) return;

        try {
            await fetch('/update_timezone', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ timezone: LOCAL_TZ })
            });
            localStorage.setItem('tz_synced', LOCAL_TZ);
        } catch (err) {
            console.warn('Could not sync time-zone:', err);
        }
    }

    // Login functionality
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
            if (data.status === 'OK') {
                await syncTimezoneWithBackend();
                window.location.href = '/chat';
            }
            else alert(data.message);
        });
    }

    // Register functionality
    const registerForm = document.getElementById('register-form');
    if (registerForm) {
        registerForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirm-password').value;
            
            if (password !== confirmPassword) {
                alert('Passwords do not match');
                return;
            }
            
            const response = await fetch('/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = await response.json();
            if (data.status === 'OK') {
                alert('Registration successful! Please login.');
                window.location.href = '/login';
            } else {
                alert(data.message);
            }
        });
    }

    // Chat selection page
    const chatListContainer = document.getElementById('chat-list-container');
    if (chatListContainer) {
        loadChatList();

        async function loadChatList() {
            try {
                const response = await fetch('/api/chats');
                const data = await response.json();
                
                if (data.status === 'OK') {
                    renderChatList(data.chats);
                } else {
                    console.error('Error loading chats:', data.message);
                }
            } catch (error) {
                console.error('Error loading chats:', error);
            }
        }

        function renderChatList(chats) {
            if (chats.length === 0) {
                chatListContainer.innerHTML = `
                    <div class="flex flex-col items-center justify-center py-12">
                        <svg class="w-12 h-12 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path>
                        </svg>
                        <p class="text-gray-500 mb-2">No conversations yet</p>
                        <a href="/new_chat" class="text-blue-500 hover:text-blue-600 font-medium">Start a new chat</a>
                    </div>`;
                return;
            }

            const chatListHTML = chats.map(chat => {
                const chatName = getChatDisplayName(chat);
                const chatType = chat.type === 'group' ? 'Group' : 'Direct';
                const lastMessageTime = chat.last_message ? formatTimeSince(chat.last_message.timestamp) : '';
                const lastMessagePreview = chat.last_message ? 
                    `${chat.last_message.sender}: ${truncateMessage(chat.last_message.message)}` : 
                    'No messages yet';
                
                return `
                    <li>
                        <a href="/chat/${chat.id}" class="flex items-center px-4 py-3 hover:bg-gray-50 transition duration-200">
                            <div class="flex-shrink-0">
                                <div class="h-10 w-10 rounded-full bg-gray-300 flex items-center justify-center text-lg font-medium text-gray-600">
                                    ${chatName.charAt(0).toUpperCase()}
                                </div>
                            </div>
                            <div class="ml-3 flex-grow">
                                <div class="flex items-center justify-between">
                                    <p class="text-sm font-medium text-gray-900">${chatName}</p>
                                    <span class="text-xs text-gray-500">${lastMessageTime}</span>
                                </div>
                                <div class="flex items-center">
                                    <p class="text-xs text-gray-400 truncate">${lastMessagePreview}</p>
                                    <span class="text-xs text-gray-400 ml-auto">${chatType}</span>
                                </div>
                            </div>
                        </a>
                    </li>`;
            }).join('');

            chatListContainer.innerHTML = `<ul class="divide-y divide-gray-200">${chatListHTML}</ul>`;
        }

        function getChatDisplayName(chat) {
            const currentUsername = window.currentUsername || document.body.dataset.username;
            
            if (chat.type === 'direct') {
                // For direct chats, show the other person's name
                const otherParticipant = chat.participants.find(p => p.username !== currentUsername);
                return otherParticipant ? otherParticipant.username : 'Unknown';
            } else {
                // For group chats, show custom name or list of other participants
                if (chat.name) {
                    return chat.name;
                } else {
                    const otherParticipants = chat.participants
                        .filter(p => p.username !== currentUsername)
                        .map(p => p.username)
                        .sort();
                    return otherParticipants.slice(0, 3).join(', ') + 
                           (otherParticipants.length > 3 ? ` +${otherParticipants.length - 3}` : '');
                }
            }
        }

        function formatTimeSince(timestamp) {
            const now = Date.now() / 1000;
            const diff = now - timestamp;
            
            if (diff < 60) return 'just now';
            if (diff < 3600) return `${Math.floor(diff / 60)}m`;
            if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
            return `${Math.floor(diff / 86400)}d`;
        }

        function truncateMessage(message, maxLength = 30) {
            if (message.length <= maxLength) return message;
            return message.substring(0, maxLength) + '...';
        }
    }

    // Individual chat page
    const sendForm = document.getElementById('send-form');
    if (sendForm) {
        const chatId = window.chatData?.chatId || parseInt(window.location.pathname.split('/').pop());
        const username = window.chatData?.username || document.body.dataset.username;
        const userId = window.chatData?.userId || document.body.dataset.userId;
        const historyContainer = document.getElementById('chat-container');
        const messageInput = document.getElementById('message');
        const socket = io();

        let renderedDateHeaders = new Set();
        let participants = [];

        // Initialize chat
        initializeChat();

        // Auto-focus the message input
        messageInput.focus();

        // Join the chat room
        socket.on('connect', () => {
            socket.emit('join_chat', { chat_id: chatId });
        });

        // Listen for new messages
        socket.on('new_message', (data) => {
            if (data.chat_id === chatId) {
                renderNewMessage(data);
            }
        });

        // Listen for user additions
        socket.on('user_added', (data) => {
            if (data.chat_id === chatId) {
                const notification = `${data.added_by} added ${data.username} to the chat`;
                renderSystemMessage(notification);
                // Reload participants
                loadChatParticipants();
            }
        });

        // Listen for chat renames
        socket.on('chat_renamed', (data) => {
            if (data.chat_id === chatId) {
                document.getElementById('chat-name').textContent = data.new_name;
                const notification = `${data.renamed_by} renamed the chat to "${data.new_name}"`;
                renderSystemMessage(notification);
            }
        });

        // Send message
        sendForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const message = messageInput.value.trim();
            if (!message) return;

            try {
                const response = await fetch('/api/send_message', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ chat_id: chatId, message })
                });

                if (response.ok) {
                    messageInput.value = '';
                    messageInput.focus();
                } else {
                    const data = await response.json();
                    alert('Error sending message: ' + data.message);
                }
            } catch (error) {
                console.error('Error sending message:', error);
                alert('Error sending message');
            }
        });

        // Add user button
        const addUserBtn = document.getElementById('add-user-btn');
        if (addUserBtn) {
            addUserBtn.addEventListener('click', () => {
                showAddUserDialog();
            });
        }

        // Edit name button
        const editNameBtn = document.getElementById('edit-name-btn');
        if (editNameBtn) {
            editNameBtn.addEventListener('click', () => {
                showEditNameDialog();
            });
        }

        async function initializeChat() {
            const loadingElement = document.getElementById('loading');
            if (loadingElement) loadingElement.remove();

            // Load existing messages
            if (window.chatData?.messages) {
                participants = window.chatData.participants || [];
                renderMessages(window.chatData.messages);
            } else {
                // Fetch chat data if not provided
                try {
                    const response = await fetch(`/api/chat/${chatId}`);
                    const data = await response.json();
                    if (data.status === 'OK') {
                        participants = data.chat.participants;
                        renderMessages(data.chat.messages);
                    }
                } catch (error) {
                    console.error('Error loading chat:', error);
                }
            }
        }

        function renderMessages(messages) {
            renderedDateHeaders.clear();
            historyContainer.innerHTML = '';
            
            messages.forEach(msg => {
                renderMessage(msg);
            });
            
            historyContainer.scrollTop = historyContainer.scrollHeight;
        }

        function renderMessage(msg) {
            const formatted = formatTimestamp(msg.timestamp);
            addDateHeaderIfNeeded(formatted.date);

            const isFromCurrentUser = msg.sender === username || msg.sender_id === parseInt(userId);
            const alignment = isFromCurrentUser ? 'text-right' : 'text-left';
            const bgColor = isFromCurrentUser ? 'bg-blue-500 text-white' : 'bg-gray-300 text-gray-800';
            
            const messageHTML = `
                <div class="${alignment} mb-2">
                    <span class="${bgColor} rounded px-3 py-1 inline-block">
                        ${escapeHtml(msg.message)}
                    </span>
                    <span class="text-xs text-gray-500">${formatted.time}</span>
                </div>`;
            
            historyContainer.insertAdjacentHTML('beforeend', messageHTML);
        }

        function renderNewMessage(data) {
            const msg = {
                sender: data.sender,
                sender_id: data.sender_id,
                message: data.message,
                timestamp: data.timestamp
            };
            renderMessage(msg);
            historyContainer.scrollTop = historyContainer.scrollHeight;
        }

        function renderSystemMessage(message) {
            const messageHTML = `
                <div class="text-center my-2">
                    <span class="bg-gray-200 text-gray-600 px-2 py-1 rounded text-xs">
                        ${escapeHtml(message)}
                    </span>
                </div>`;
            historyContainer.insertAdjacentHTML('beforeend', messageHTML);
            historyContainer.scrollTop = historyContainer.scrollHeight;
        }

        function formatTimestamp(timestamp) {
            const date = new Date(timestamp * 1000);
            return {
                date: date.toLocaleDateString('en-CA'),
                time: date.toLocaleTimeString('en-US', { 
                    hour: '2-digit', 
                    minute: '2-digit', 
                    hour12: false 
                })
            };
        }

        function addDateHeaderIfNeeded(dateString) {
            const dateHeader = getDateHeader(dateString);
            if (!renderedDateHeaders.has(dateHeader)) {
                const headerHtml = `
                    <div class="text-center my-4">
                        <span class="bg-gray-200 text-gray-600 px-3 py-1 rounded-full text-sm font-medium">
                            ${dateHeader}
                        </span>
                    </div>`;
                historyContainer.insertAdjacentHTML('beforeend', headerHtml);
                renderedDateHeaders.add(dateHeader);
            }
        }

        function getDateHeader(dateString) {
            const messageDate = new Date(dateString + 'T00:00:00');
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            
            const yesterday = new Date(today);
            yesterday.setDate(yesterday.getDate() - 1);
            
            const oneWeekAgo = new Date(today);
            oneWeekAgo.setDate(oneWeekAgo.getDate() - 7);

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

        async function showAddUserDialog() {
            const username = prompt('Enter username to add to this chat:');
            if (!username || username === window.chatData.username) return;

            try {
                const response = await fetch('/api/add_user_to_chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ chat_id: chatId, username })
                });

                const data = await response.json();
                if (data.status === 'OK') {
                    // Success message will come through WebSocket
                } else {
                    alert('Error: ' + data.message);
                }
            } catch (error) {
                console.error('Error adding user:', error);
                alert('Error adding user to chat');
            }
        }

        async function loadChatParticipants() {
            try {
                const response = await fetch(`/api/chat/${chatId}`);
                const data = await response.json();
                if (data.status === 'OK') {
                    participants = data.chat.participants;
                    updateChatHeader();
                }
            } catch (error) {
                console.error('Error loading participants:', error);
            }
        }

        function updateChatHeader() {
            // Update the header with new participant list if needed
            const names = participants
                          .map(p => p.username)
                          .filter(u => u !== username)
                          .join(', ');

            // subtitle
            const subtitleEl = document.getElementById('chat-header-participants');
            if (subtitleEl) subtitleEl.textContent = names;

            // title (only when the DB name is blank)
            const titleEl = document.getElementById('chat-name');
            if (titleEl && titleEl.dataset.custom === '0') {
                titleEl.textContent = names;
            }
        }

        async function showEditNameDialog() {
            const currentName = document.getElementById('chat-name').textContent.trim();
            const newName = prompt('Enter new chat name:', currentName);
            if (newName === null) return;

            try {
                const response = await fetch('/api/update_chat_name', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ chat_id: chatId, name: newName.trim() })
                });

                const data = await response.json();
                if (data.status !== 'OK') {
                    alert('Error: ' + data.message);
                }
                if (!newName) {
                    const currentUsername = window.chatData.username
                    const allParticipants = participants
                    .filter(p => p.username !== currentUsername)
                    .map(p => p.username)
                    .sort()
                    .join(', ')
                    .trim();
                    document.getElementById('chat-name').textContent = allParticipants;
                }
                // Set custom flag for `addUserToChat` updates
                document.getElementById('chat-name').dataset.custom = newName === '' ? '0' : '1';
            } catch (error) {
                console.error('Error renaming chat:', error);
                alert('Error renaming chat');
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    }

    // New chat page with email-like recipient input
    const newChatForm = document.getElementById('new-chat-form');
    if (newChatForm) {
        const recipientInput = document.getElementById('recipient-input');
        const recipientContainer = document.getElementById('recipient-container');
        const selectedRecipients = new Set();
        let allUsers = [];

        // Load all users for autocomplete
        loadAllUsers();

        async function loadAllUsers() {
            try {
                const response = await fetch('/api/users');
                const data = await response.json();
                if (data.status === 'OK') {
                    allUsers = data.users;
                    setupAutocomplete();
                }
            } catch (error) {
                console.error('Error loading users:', error);
            }
        }

        function setupAutocomplete() {
            const datalist = document.createElement('datalist');
            datalist.id = 'users-datalist';
            allUsers.forEach(user => {
                const option = document.createElement('option');
                option.value = user;
                datalist.appendChild(option);
            });
            document.body.appendChild(datalist);
            recipientInput.setAttribute('list', 'users-datalist');
        }

        // Handle space key to add recipient
        recipientInput.addEventListener('keydown', (e) => {
            if (e.key === ' ' || e.key === 'Enter') {
                e.preventDefault();
                const username = recipientInput.value.trim();
                if (username && !selectedRecipients.has(username)) {
                    if (allUsers.includes(username)) {
                        addRecipientChip(username);
                        recipientInput.value = '';
                    } else {
                        alert(`User "${username}" not found`);
                    }
                }
            }
        });

        // Handle form submission
        newChatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            // Check for any text in input field
            const pendingUsername = recipientInput.value.trim();
            if (pendingUsername && !selectedRecipients.has(pendingUsername)) {
                if (allUsers.includes(pendingUsername)) {
                    addRecipientChip(pendingUsername);
                    recipientInput.value = '';
                }
            }

            if (selectedRecipients.size === 0) {
                alert('Please add at least one recipient');
                return;
            }

            try {
                const response = await fetch('/api/create_chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        participants: Array.from(selectedRecipients)
                    })
                });

                const data = await response.json();
                if (data.status === 'OK') {
                    // Redirect to the new chat
                    window.location.href = `/chat/${data.chat_id}`;
                } else {
                    alert('Error creating chat: ' + data.message);
                }
            } catch (error) {
                console.error('Error creating chat:', error);
                alert('Error creating chat');
            }
        });

        function addRecipientChip(username) {
            selectedRecipients.add(username);

            const chip = document.createElement('span');
            chip.className = 'inline-flex items-center px-3 py-1 rounded-full text-sm bg-gray-200 text-gray-800 mr-2 mb-2';
            chip.innerHTML = `
                ${escapeHtml(username)}
                <button type="button" class="ml-2 text-gray-500 hover:text-gray-700" data-username="${username}">
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
                    </svg>
                </button>
            `;

            const removeBtn = chip.querySelector('button');
            removeBtn.addEventListener('click', () => {
                selectedRecipients.delete(username);
                chip.remove();
                updateRecipientDisplay();
            });

            recipientContainer.appendChild(chip);
            updateRecipientDisplay();
        }

        function updateRecipientDisplay() {
            if (selectedRecipients.size > 0) {
                recipientContainer.classList.remove('hidden');
            } else {
                recipientContainer.classList.add('hidden');
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    }
});
