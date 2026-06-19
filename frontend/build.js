const fs = require('fs');
const path = require('path');

const backendUrl = process.env.BACKEND_URL || process.env.RENDER_URL || '';

const configContent = `// Frontend Production & Local Configuration
const CONFIG = {
    // If hosted locally, it will default to window.location.origin (e.g. http://127.0.0.1:8000).
    // If hosted on Vercel, it will use the build-time BACKEND_URL or fallback to the default Render URL.
    BACKEND_URL: ${backendUrl ? `"${backendUrl}"` : `((window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1" || window.location.hostname === "") ? window.location.origin : "https://sentinel-traffic-backend.onrender.com")`}
};
`;

const configPath = path.join(__dirname, 'config.js');
fs.writeFileSync(configPath, configContent);
console.log(`Successfully generated config.js (BACKEND_URL is ${backendUrl ? backendUrl : 'dynamic fallback (localhost or default Render)'})`);
