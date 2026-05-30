const statusText = document.getElementById('status-text');
const commandText = document.getElementById('command-text');
const orb = document.getElementById('sundar-orb');

let ws;
let reconnectInterval;

function connect() {
  ws = new WebSocket('ws://127.0.0.1:8000/ws');

  ws.onopen = () => {
    console.log('Connected to Backend');
    if (reconnectInterval) clearInterval(reconnectInterval);
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.status) {
        statusText.textContent = data.status;
        updateOrbState(data.status);
      }
      if (data.last_command) {
        commandText.textContent = `"${data.last_command}"`;
      }
    } catch (e) {
      console.error('Error parsing WS message', e);
    }
  };

  ws.onclose = () => {
    statusText.textContent = 'Disconnected. Reconnecting...';
    orb.className = 'orb pulse-idle';
    orb.style.filter = 'grayscale(100%)';
    reconnectInterval = setTimeout(connect, 3000);
  };
}

function updateOrbState(status) {
  orb.style.filter = 'none';
  const lowerStatus = status.toLowerCase();
  if (lowerStatus.includes('listening')) {
    orb.className = 'orb pulse-active';
  } else if (lowerStatus.includes('speaking')) {
    orb.className = 'orb pulse-speaking';
  } else {
    orb.className = 'orb pulse-idle';
  }
}

connect();
