// Frontend Production & Local Configuration
const CONFIG = {
    // If hosted locally, it will default to window.location.origin (e.g. http://127.0.0.1:8000).
    // If hosted on Vercel, it will use the build-time BACKEND_URL or fallback to the default Render URL.
    BACKEND_URL: ("__BACKEND_URL_PLACEHOLDER__".startsWith("http") && !"__BACKEND_URL_PLACEHOLDER__".includes("PLACEHOLDER"))
        ? "__BACKEND_URL_PLACEHOLDER__"
        : ((window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1" || window.location.hostname === "")
            ? window.location.origin
            : "https://sentinel-traffic-backend.onrender.com") // Fallback production URL
};

