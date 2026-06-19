// Traffic Rules Violation Detection System - Monitor Console UI Logic

// Intercept relative fetch calls to point to the correct backend host
const originalFetch = window.fetch;
window.fetch = function (url, options) {
    if (typeof url === "string" && url.startsWith("/")) {
        url = CONFIG.BACKEND_URL + url;
    }
    return originalFetch(url, options);
};


// State management
let state = {
    selectedVideo: "",
    previewData: null,
    points: [],
    signalState: "RED",
    mode: "signal", // "signal", "direction", "parking", "triple_riding", "helmet"
    allowedDirection: "normal",
    parkingTimeLimit: 5.0,
    maxAllowedRiders: 2,
    inferenceSource: "local",
    isLineSaved: false,
    statsInterval: null,
    isStreamActive: false,
    allViolations: [],
    selectedQueryId: "",
    inspectorRecord: null,
    typeChart: null,
    locationChart: null
};

// UI Elements
const els = {
    connectionStatus: document.getElementById("connectionStatus"),
    videoSelect: document.getElementById("videoSelect"),
    videoUpload: document.getElementById("videoUpload"),
    uploadBtn: document.getElementById("uploadBtn"),
    uploadProgress: document.getElementById("uploadProgress"),
    
    // Tabs
    tabSignalBtn: document.getElementById("tabSignalBtn"),
    tabDirectionBtn: document.getElementById("tabDirectionBtn"),
    tabParkingBtn: document.getElementById("tabParkingBtn"),
    tabTripleBtn: document.getElementById("tabTripleBtn"),
    tabHelmetBtn: document.getElementById("tabHelmetBtn"),
    
    // Configurations
    configSignalSection: document.getElementById("configSignalSection"),
    configDirectionSection: document.getElementById("configDirectionSection"),
    configParkingSection: document.getElementById("configParkingSection"),
    configTripleSection: document.getElementById("configTripleSection"),
    configHelmetSection: document.getElementById("configHelmetSection"),
    
    signalToggleBtn: document.getElementById("signalToggleBtn"),
    signalStateText: document.getElementById("signalStateText"),
    lightRed: document.getElementById("lightRed"),
    lightGreen: document.getElementById("lightGreen"),
    
    directionSelect: document.getElementById("directionSelect"),
    saveDirectionBtn: document.getElementById("saveDirectionBtn"),
    
    parkingTimeInput: document.getElementById("parkingTimeInput"),
    saveParkingBtn: document.getElementById("saveParkingBtn"),
    
    maxRidersInput: document.getElementById("maxRidersInput"),
    tripleSourceSelect: document.getElementById("tripleSourceSelect"),
    saveTripleBtn: document.getElementById("saveTripleBtn"),
    
    helmetSourceSelect: document.getElementById("helmetSourceSelect"),
    saveHelmetBtn: document.getElementById("saveHelmetBtn"),
    
    // Canvas Drawing
    roiSection: document.getElementById("roiSection"),
    roiCanvas: document.getElementById("roiCanvas"),
    canvasPlaceholder: document.getElementById("canvasPlaceholder"),
    roiInstructions: document.getElementById("roiInstructions"),
    saveLineBtn: document.getElementById("saveLineBtn"),
    clearLineBtn: document.getElementById("clearLineBtn"),
    
    // Monitor
    analysisStatusText: document.getElementById("analysisStatusText"),
    progressBarFill: document.getElementById("progressBarFill"),
    progressBarText: document.getElementById("progressBarText"),
    analysisStatsFeedback: document.getElementById("analysisStatsFeedback"),
    startBtn: document.getElementById("startBtn"),
    stopBtn: document.getElementById("stopBtn"),
    videoFeed: document.getElementById("videoFeed"),
    videoPlaceholder: document.getElementById("videoPlaceholder"),
    samplingIntervalInput: document.getElementById("samplingIntervalInput"),
    
    // Stats
    statTotalVehicles: document.getElementById("statTotalVehicles"),
    statTotalViolations: document.getElementById("statTotalViolations"),
    statActiveMode: document.getElementById("statActiveMode"),
    
    countCar: document.getElementById("countCar"),
    countMotorcycle: document.getElementById("countMotorcycle"),
    countBus: document.getElementById("countBus"),
    countTruck: document.getElementById("countTruck"),
    countBicycle: document.getElementById("countBicycle"),
    
    clearLogBtn: document.getElementById("clearLogBtn"),
    violationsLogBody: document.getElementById("violationsLogBody"),
    
    // Lightbox Modal
    cropModal: document.getElementById("cropModal"),
    cropModalImg: document.getElementById("cropModalImg"),
    modalClose: document.querySelector(".modal-close"),
    modalTitle: document.getElementById("modalTitle"),
    modalDetails: document.getElementById("modalDetails"),

    // Main navigation tabs & views
    navTabAnalytics: document.getElementById("navTabAnalytics"),
    navTabControlPanel: document.getElementById("navTabControlPanel"),
    navTabQueries: document.getElementById("navTabQueries"),
    navTabInspector: document.getElementById("navTabInspector"),
    
    viewAnalytics: document.getElementById("viewAnalytics"),
    viewControlPanel: document.getElementById("viewControlPanel"),
    viewQueries: document.getElementById("viewQueries"),
    viewInspector: document.getElementById("viewInspector"),

    // Analytics View Elements
    anaTotalViolations: document.getElementById("anaTotalViolations"),
    anaFinesCollected: document.getElementById("anaFinesCollected"),
    anaFinesPending: document.getElementById("anaFinesPending"),
    anaActiveDisputes: document.getElementById("anaActiveDisputes"),
    anaFilterSearch: document.getElementById("anaFilterSearch"),
    anaFilterLocation: document.getElementById("anaFilterLocation"),
    anaFilterType: document.getElementById("anaFilterType"),
    anaFilterStatus: document.getElementById("anaFilterStatus"),
    anaViolationsLogBody: document.getElementById("anaViolationsLogBody"),

    // Dispute View Elements
    queryInboxList: document.getElementById("queryInboxList"),
    queryDetailPanel: document.getElementById("queryDetailPanel"),
    queryPlaceholderPanel: document.getElementById("queryPlaceholderPanel"),
    queryDetailTitle: document.getElementById("queryDetailTitle"),
    queryDetailSub: document.getElementById("queryDetailSub"),
    queryDetailBadge: document.getElementById("queryDetailBadge"),
    queryDetailName: document.getElementById("queryDetailName"),
    queryDetailMobile: document.getElementById("queryDetailMobile"),
    queryDetailVehicle: document.getElementById("queryDetailVehicle"),
    queryDetailPlate: document.getElementById("queryDetailPlate"),
    queryDetailImg: document.getElementById("queryDetailImg"),
    queryAdminChatBox: document.getElementById("queryAdminChatBox"),
    queryAdminInput: document.getElementById("queryAdminInput"),
    queryAdminSendBtn: document.getElementById("queryAdminSendBtn"),
    queryAdminDismissBtn: document.getElementById("queryAdminDismissBtn"),
    queryAdminUpholdBtn: document.getElementById("queryAdminUpholdBtn"),

    // Video Inspector Elements
    inspectorSearchId: document.getElementById("inspectorSearchId"),
    inspectorSearchBtn: document.getElementById("inspectorSearchBtn"),
    inspectorContentPanel: document.getElementById("inspectorContentPanel"),
    inspectorVideoPlayer: document.getElementById("inspectorVideoPlayer"),
    inspectorJumpTimeBtn: document.getElementById("inspectorJumpTimeBtn"),
    insReportId: document.getElementById("insReportId"),
    insReportType: document.getElementById("insReportType"),
    insReportLocation: document.getElementById("insReportLocation"),
    insReportName: document.getElementById("insReportName"),
    insReportVideo: document.getElementById("insReportVideo"),
    insReportTimestamp: document.getElementById("insReportTimestamp"),
    insReportPlate: document.getElementById("insReportPlate"),
    insReportCropImg: document.getElementById("insReportCropImg"),
    inspectorErrorPanel: document.getElementById("inspectorErrorPanel")
};

// Canvas drawing setup
const ctx = els.roiCanvas.getContext("2d");
let previewImage = new Image();

// Initial Setup
function init() {
    registerEventListeners();
    checkBackendConnection();
    loadVideos();
    switchTab("signal"); // Default Mode inside Control Panel
    switchMainTab("analytics"); // Default View of the SPA
}

// Event Listeners Registration
function registerEventListeners() {
    els.videoSelect.addEventListener("change", onVideoSelect);
    els.uploadBtn.addEventListener("click", uploadVideo);
    els.signalToggleBtn.addEventListener("click", toggleSignalState);
    if (els.saveDirectionBtn) els.saveDirectionBtn.addEventListener("click", saveDirectionConfig);
    if (els.saveParkingBtn) els.saveParkingBtn.addEventListener("click", saveParkingConfig);
    if (els.saveTripleBtn) els.saveTripleBtn.addEventListener("click", saveTripleConfig);
    if (els.saveHelmetBtn) els.saveHelmetBtn.addEventListener("click", saveHelmetConfig);
    
    els.roiCanvas.addEventListener("click", onCanvasClick);
    els.clearLineBtn.addEventListener("click", resetCanvas);
    els.saveLineBtn.addEventListener("click", saveROICoordinates);
    
    els.startBtn.addEventListener("click", startDetection);
    els.stopBtn.addEventListener("click", stopDetection);
    els.clearLogBtn.addEventListener("click", clearViolationsLog);
    
    // Tab Selectors
    els.tabSignalBtn.addEventListener("click", () => switchTab("signal"));
    els.tabDirectionBtn.addEventListener("click", () => switchTab("direction"));
    els.tabParkingBtn.addEventListener("click", () => switchTab("parking"));
    els.tabTripleBtn.addEventListener("click", () => switchTab("triple_riding"));
    els.tabHelmetBtn.addEventListener("click", () => switchTab("helmet"));
    
    // Lightbox modal close listeners
    els.modalClose.addEventListener("click", () => {
        els.cropModal.style.display = "none";
    });
    window.addEventListener("click", (e) => {
        if (e.target === els.cropModal) {
            els.cropModal.style.display = "none";
        }
    });

    // Analytics Filters
    els.anaFilterSearch.addEventListener("input", filterAnalytics);
    els.anaFilterLocation.addEventListener("change", filterAnalytics);
    els.anaFilterType.addEventListener("change", filterAnalytics);
    els.anaFilterStatus.addEventListener("change", filterAnalytics);

    // Disputes Panel
    els.queryAdminSendBtn.addEventListener("click", sendAdminQueryReply);
    els.queryAdminInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") sendAdminQueryReply();
    });
    els.queryAdminDismissBtn.addEventListener("click", waiveChallan);
    els.queryAdminUpholdBtn.addEventListener("click", rejectDispute);

    // Inspector
    els.inspectorSearchBtn.addEventListener("click", searchInspectionRecord);
    els.inspectorSearchId.addEventListener("keydown", (e) => {
        if (e.key === "Enter") searchInspectionRecord();
    });
    els.inspectorJumpTimeBtn.addEventListener("click", jumpToInspectorTime);
}

// Check if Backend API is running
async function checkBackendConnection() {
    try {
        const res = await fetch("/videos");
        if (res.ok) {
            els.connectionStatus.textContent = "CONNECTED (ONLINE)";
            els.connectionStatus.className = "status-indicator online";
        } else {
            throw new Error("HTTP Error");
        }
    } catch (e) {
        els.connectionStatus.textContent = "OFFLINE (RETRYING)";
        els.connectionStatus.className = "status-indicator offline";
        setTimeout(checkBackendConnection, 5000);
    }
}

// Switch Active Detection Mode Tab
function switchTab(newMode) {
    if (state.isStreamActive) {
        alert("Cannot switch tabs while detection is active. Please Stop Detection first.");
        return;
    }
    
    state.mode = newMode;
    resetCanvas();
    
    // Update Tab Button Styles
    els.tabSignalBtn.className = "tab-btn" + (newMode === "signal" ? " active" : "");
    els.tabDirectionBtn.className = "tab-btn" + (newMode === "direction" ? " active" : "");
    els.tabParkingBtn.className = "tab-btn" + (newMode === "parking" ? " active" : "");
    els.tabTripleBtn.className = "tab-btn" + (newMode === "triple_riding" ? " active" : "");
    els.tabHelmetBtn.className = "tab-btn" + (newMode === "helmet" ? " active" : "");
    
    // Show/Hide configuration segments
    els.configSignalSection.style.display = newMode === "signal" ? "block" : "none";
    els.configDirectionSection.style.display = newMode === "direction" ? "block" : "none";
    els.configParkingSection.style.display = newMode === "parking" ? "block" : "none";
    els.configTripleSection.style.display = newMode === "triple_riding" ? "block" : "none";
    els.configHelmetSection.style.display = newMode === "helmet" ? "block" : "none";
    
    // Show/Hide ROI selection section based on mode
    if (newMode === "triple_riding" || newMode === "helmet") {
        els.roiSection.style.display = "none";
        els.startBtn.disabled = !state.selectedVideo;
    } else {
        els.roiSection.style.display = "block";
        els.startBtn.disabled = !(state.selectedVideo && state.isLineSaved);
    }
    
    // Update labels and instructions
    if (newMode === "parking") {
        els.roiInstructions.textContent = "Instructions: Select a video first. Click twice on the preview frame below to define the opposite corners (top-left and bottom-right) of the No-Parking rectangular zone.";
        els.statActiveMode.textContent = "No Parking";
    } else if (newMode === "direction") {
        els.roiInstructions.textContent = "Instructions: Select a video first. Click twice on the preview frame below to draw the virtual line checkpoint.";
        els.statActiveMode.textContent = "Wrong Way";
    } else if (newMode === "triple_riding") {
        els.roiInstructions.textContent = "Instructions: Select a video first. Click twice on the preview frame below to draw the virtual line checkpoint.";
        els.statActiveMode.textContent = "Triple Rider";
    } else if (newMode === "helmet") {
        els.roiInstructions.textContent = "Instructions: Select a video first. Click twice on the preview frame below to draw the virtual line checkpoint.";
        els.statActiveMode.textContent = "Helmet Violation";
    } else {
        els.roiInstructions.textContent = "Instructions: Select a video first. Click twice on the preview frame below to draw the virtual line checkpoint.";
        els.statActiveMode.textContent = "Traffic Signal";
    }
    
    // Reload preview if a video is selected
    if (state.selectedVideo) {
        onVideoSelect();
    }
}

// Load Video List from Server
async function loadVideos() {
    try {
        const res = await fetch("/videos");
        if (!res.ok) throw new Error("Could not fetch videos");
        const videos = await res.json();
        
        els.videoSelect.innerHTML = '<option value="">-- Choose Video --</option>';
        videos.forEach(v => {
            const opt = document.createElement("option");
            opt.value = v.name;
            opt.textContent = `${v.name} (${v.size})`;
            els.videoSelect.appendChild(opt);
        });
        
        if (state.selectedVideo) {
            els.videoSelect.value = state.selectedVideo;
        }
    } catch (e) {
        console.error("Failed to load video list:", e);
    }
}

// Upload custom video file
async function uploadVideo() {
    const file = els.videoUpload.files[0];
    if (!file) {
        alert("Please select a file to upload first.");
        return;
    }
    
    els.uploadProgress.textContent = "Uploading... Please wait.";
    els.uploadBtn.disabled = true;
    
    const formData = new FormData();
    formData.append("file", file);
    
    try {
        const res = await fetch("/upload", {
            method: "POST",
            body: formData
        });
        
        if (!res.ok) throw new Error("Upload failed");
        
        els.uploadProgress.textContent = "Upload successful!";
        els.videoUpload.value = ""; 
        await loadVideos();
    } catch (e) {
        console.error(e);
        els.uploadProgress.textContent = "Error during upload.";
    } finally {
        els.uploadBtn.disabled = false;
        setTimeout(() => { els.uploadProgress.textContent = ""; }, 5000);
    }
}

// Triggered when a video is selected from dropdown
async function onVideoSelect() {
    state.selectedVideo = els.videoSelect.value;
    resetCanvas();
    
    if (!state.selectedVideo) {
        els.canvasPlaceholder.style.display = "flex";
        els.canvasPlaceholder.textContent = "Select a video to load preview frame";
        els.startBtn.disabled = true;
        return;
    }
    
    els.canvasPlaceholder.textContent = "Extracting preview frame... Please wait.";
    els.canvasPlaceholder.style.display = "flex";
    
    try {
        const res = await fetch(`/preview?filename=${encodeURIComponent(state.selectedVideo)}`);
        if (!res.ok) throw new Error("Could not load preview frame");
        
        state.previewData = await res.json();
        
        // Load the preview frame image onto canvas (onload must be set BEFORE src to avoid caching race condition)
        previewImage.onload = () => {
            els.roiCanvas.width = state.previewData.width;
            els.roiCanvas.height = state.previewData.height;
            els.canvasPlaceholder.style.display = "none";
            drawOverlay();
        };
        previewImage.src = state.previewData.url;
        
        if (state.mode === "triple_riding" || state.mode === "helmet") {
            els.startBtn.disabled = false;
        }
    } catch (e) {
        console.error("Preview loading error:", e);
        els.canvasPlaceholder.textContent = "Error: Could not retrieve frame preview.";
    }
}

// Draw the preview image, registered points, and lines/boxes
function drawOverlay() {
    if (!state.previewData) return;
    
    // Paint the clean frame
    ctx.drawImage(previewImage, 0, 0);
    
    // Choose color scheme: Red for parking, Blue for signal/direction
    const schemeColor = state.mode === "parking" ? "#ff0000" : "#0000ff";
    
    // Draw coordinates & shapes
    if (state.points.length > 0) {
        ctx.fillStyle = schemeColor;
        ctx.strokeStyle = schemeColor;
        ctx.lineWidth = 4;
        
        state.points.forEach((p, idx) => {
            ctx.beginPath();
            ctx.arc(p.x, p.y, 8, 0, 2 * Math.PI);
            ctx.fill();
            
            ctx.fillStyle = "#ffffff";
            ctx.font = "bold 20px Arial";
            ctx.fillText(`P${idx + 1}`, p.x + 12, p.y + 6);
            ctx.fillStyle = schemeColor;
        });
        
        if (state.points.length === 2) {
            const p1 = state.points[0];
            const p2 = state.points[1];
            
            if (state.mode === "parking") {
                // Draw bounding box rectangle
                ctx.strokeRect(p1.x, p1.y, p2.x - p1.x, p2.y - p1.y);
            } else {
                // Draw checkpoint segment line
                ctx.beginPath();
                ctx.moveTo(p1.x, p1.y);
                ctx.lineTo(p2.x, p2.y);
                ctx.stroke();
            }
        }
    }
}

// Canvas Click Event Handler
function onCanvasClick(e) {
    if (!state.previewData) return;
    if (state.points.length >= 2) return; 
    
    const rect = els.roiCanvas.getBoundingClientRect();
    const scaleX = els.roiCanvas.width / rect.width;
    const scaleY = els.roiCanvas.height / rect.height;
    
    const x = (e.clientX - rect.left) * scaleX;
    const y = (e.clientY - rect.top) * scaleY;
    
    state.points.push({ x: Math.round(x), y: Math.round(y) });
    drawOverlay();
    
    if (state.points.length === 2) {
        els.saveLineBtn.disabled = false;
    }
}

// Reset Canvas Points
function resetCanvas() {
    state.points = [];
    state.isLineSaved = false;
    els.saveLineBtn.disabled = true;
    els.startBtn.disabled = true;
    
    if (state.previewData) {
        drawOverlay();
    }
}

// Save ROI coordinates to backend API
async function saveROICoordinates() {
    if (state.points.length !== 2) return;
    
    const payload = {
        x1: state.points[0].x,
        y1: state.points[0].y,
        x2: state.points[1].x,
        y2: state.points[1].y,
        mode: state.mode
    };
    
    try {
        const res = await fetch("/set_roi", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        
        if (!res.ok) throw new Error("API call failed");
        
        state.isLineSaved = true;
        els.saveLineBtn.disabled = true;
        els.startBtn.disabled = false; // Enable stream detection!
        
        const shapeStr = state.mode === "parking" ? "Rectangle region" : "Checkpoint segment";
        alert(`Success: Boundary coordinates locked! \n${shapeStr}: (${payload.x1}, ${payload.y1}) to (${payload.x2}, ${payload.y2})`);
    } catch (e) {
        console.error("Save ROI failed:", e);
        alert("Error: Failed to register ROI coordinates on backend.");
    }
}

// Toggle traffic light state (RED vs GREEN)
async function toggleSignalState() {
    const nextState = state.signalState === "RED" ? "GREEN" : "RED";
    
    try {
        const res = await fetch("/toggle_signal", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ state: nextState })
        });
        
        if (!res.ok) throw new Error("API call failed");
        
        state.signalState = nextState;
        updateSignalUI();
    } catch (e) {
        console.error("Toggle signal state error:", e);
    }
}

// Synchronize Signal State visual styles
function updateSignalUI() {
    if (state.signalState === "RED") {
        els.signalToggleBtn.textContent = "SIGNAL LIGHT STATE: RED";
        els.signalToggleBtn.className = "gov-btn signal-btn red-active";
        
        els.lightRed.classList.add("active");
        els.lightGreen.classList.remove("active");
    } else {
        els.signalToggleBtn.textContent = "SIGNAL LIGHT STATE: GREEN";
        els.signalToggleBtn.className = "gov-btn signal-btn green-active";
        
        els.lightRed.classList.remove("active");
        els.lightGreen.classList.add("active");
    }
}

// Save Wrong Way direction configurations
async function saveDirectionConfig(showAlert = true) {
    const direction = els.directionSelect.value;
    try {
        const res = await fetch("/config/direction", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ allowed_direction: direction })
        });
        if (!res.ok) throw new Error("API failed");
        state.allowedDirection = direction;
        if (showAlert) {
            alert("Success: Direction config updated on server.");
        }
    } catch (e) {
        console.error(e);
        if (showAlert) {
            alert("Error: Failed to update direction configurations.");
        }
    }
}

// Save No-Parking time configs
async function saveParkingConfig(showAlert = true) {
    const limit = parseFloat(els.parkingTimeInput.value);
    if (isNaN(limit) || limit <= 0) {
        if (showAlert) {
            alert("Please enter a valid positive number of seconds.");
        }
        return;
    }
    
    try {
        const res = await fetch("/config/parking", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ parking_time_limit: limit })
        });
        if (!res.ok) throw new Error("API failed");
        state.parkingTimeLimit = limit;
        if (showAlert) {
            alert(`Success: Parking time threshold configured to ${limit} seconds.`);
        }
    } catch (e) {
        console.error(e);
        if (showAlert) {
            alert("Error: Failed to update parking threshold.");
        }
    }
}

// Save Triple Riding Configs
async function saveTripleConfig(showAlert = true) {
    if (!els.maxRidersInput) return;
    const limit = parseInt(els.maxRidersInput.value);
    const source = els.tripleSourceSelect ? els.tripleSourceSelect.value : "local";
    if (isNaN(limit) || limit <= 0) {
        if (showAlert) {
            alert("Please enter a valid positive number of riders.");
        }
        return;
    }
    
    try {
        const res = await fetch("/config/triple_riding", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ max_allowed_riders: limit, inference_source: source })
        });
        if (!res.ok) throw new Error("API failed");
        state.maxAllowedRiders = limit;
        state.inferenceSource = source;
        if (showAlert) {
            alert(`Success: Triple riding limit set to ${limit} riders, engine: ${source.toUpperCase()}.`);
        }
    } catch (e) {
        console.error(e);
        if (showAlert) {
            alert("Error: Failed to update triple riding configurations.");
        }
    }
}

// Save Helmet Configs
async function saveHelmetConfig(showAlert = true) {
    const source = els.helmetSourceSelect ? els.helmetSourceSelect.value : "local";
    try {
        const res = await fetch("/config/helmet", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ inference_source: source })
        });
        if (!res.ok) throw new Error("API failed");
        state.inferenceSource = source;
        if (showAlert) {
            alert(`Success: Helmet detection engine updated to ${source.toUpperCase()}.`);
        }
    } catch (e) {
        console.error(e);
        if (showAlert) {
            alert("Error: Failed to update helmet configurations.");
        }
    }
}

// Start Batch Video Processing
async function startDetection() {
    if (!state.selectedVideo) return;
    if (state.mode !== "triple_riding" && state.mode !== "helmet" && !state.isLineSaved) {
        alert("Please configure and lock ROI coordinates first.");
        return;
    }
    
    // Auto-save configurations first to ensure backend has latest values
    if (state.mode === "direction") {
        await saveDirectionConfig(false);
    } else if (state.mode === "parking") {
        await saveParkingConfig(false);
    } else if (state.mode === "triple_riding") {
        await saveTripleConfig(false);
    } else if (state.mode === "helmet") {
        await saveHelmetConfig(false);
    }
    
    state.isStreamActive = true;
    
    // Get sampling interval value
    let intervalVal = parseFloat(els.samplingIntervalInput.value) || 0.3;
    
    // Reset progress UI
    els.progressBarFill.style.width = "0%";
    els.progressBarText.textContent = "0%";
    els.analysisStatusText.textContent = "SYSTEM STATUS: INITIATING...";
    els.analysisStatusText.style.color = "#ffeb3b";
    els.analysisStatsFeedback.textContent = "Sending analysis request to server...";
    
    // Reset preview window
    els.videoFeed.src = "";
    els.videoFeed.style.display = "block";
    els.videoPlaceholder.style.display = "none";
    
    try {
        const res = await fetch("/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                filename: state.selectedVideo,
                mode: state.mode,
                sampling_interval: intervalVal
            })
        });
        
        if (!res.ok) {
            const errData = await res.json();
            throw new Error(errData.detail || "Failed to start analysis");
        }
        
        // Configure buttons
        els.startBtn.disabled = true;
        els.stopBtn.disabled = false;
        els.videoSelect.disabled = true;
        els.videoUpload.disabled = true;
        els.uploadBtn.disabled = true;
        els.clearLineBtn.disabled = true;
        els.samplingIntervalInput.disabled = true;
        
        // Disable tab selectors during running detection
        els.tabSignalBtn.disabled = true;
        els.tabDirectionBtn.disabled = true;
        els.tabParkingBtn.disabled = true;
        els.tabTripleBtn.disabled = true;
        els.tabHelmetBtn.disabled = true;
        
        els.analysisStatusText.textContent = "SYSTEM STATUS: PROCESSING...";
        els.analysisStatusText.style.color = "#ffeb3b";
        els.analysisStatsFeedback.textContent = "Analyzing video frames...";
        
        // Start Polling progress and stats every 250ms (faster for smoother previews)
        state.statsInterval = setInterval(pollAnalysisProgress, 250);
    } catch (e) {
        console.error("Failed to start analysis:", e);
        alert(`Error: ${e.message}`);
        state.isStreamActive = false;
        els.videoFeed.style.display = "none";
        els.videoPlaceholder.style.display = "flex";
        els.analysisStatusText.textContent = "SYSTEM STATUS: ERROR";
        els.analysisStatusText.style.color = "#c62828";
        els.analysisStatsFeedback.textContent = "Failed to initiate analysis on backend.";
    }
}

// Stop Video Processing
async function stopDetection() {
    state.isStreamActive = false;
    
    // Clear polling interval
    if (state.statsInterval) {
        clearInterval(state.statsInterval);
        state.statsInterval = null;
    }
    
    // Call stop API
    try {
        await fetch("/stop", { method: "POST" });
    } catch (e) {
        console.error("Failed to stop processing on backend:", e);
    }
    
    els.analysisStatusText.textContent = "SYSTEM STATUS: STOPPED";
    els.analysisStatusText.style.color = "#c62828";
    els.analysisStatsFeedback.textContent = "Analysis stopped by user.";
    
    els.videoFeed.style.display = "none";
    els.videoFeed.src = "";
    els.videoPlaceholder.style.display = "flex";
    
    // Re-enable buttons
    els.startBtn.disabled = false;
    els.stopBtn.disabled = true;
    els.videoSelect.disabled = false;
    els.videoUpload.disabled = false;
    els.uploadBtn.disabled = false;
    els.clearLineBtn.disabled = false;
    els.samplingIntervalInput.disabled = false;
    
    // Re-enable tab selectors
    els.tabSignalBtn.disabled = false;
    els.tabDirectionBtn.disabled = false;
    els.tabParkingBtn.disabled = false;
    els.tabTripleBtn.disabled = false;
    els.tabHelmetBtn.disabled = false;
}

// Complete Video Processing
function completeDetection() {
    state.isStreamActive = false;
    
    if (state.statsInterval) {
        clearInterval(state.statsInterval);
        state.statsInterval = null;
    }
    
    els.progressBarFill.style.width = "100%";
    els.progressBarText.textContent = "100%";
    els.analysisStatusText.textContent = "SYSTEM STATUS: COMPLETED";
    els.analysisStatusText.style.color = "#2e7d32";
    els.analysisStatsFeedback.textContent = "Video analysis finished successfully.\nAll violation clips generated.";
    
    // Re-enable buttons
    els.startBtn.disabled = false;
    els.stopBtn.disabled = true;
    els.videoSelect.disabled = false;
    els.videoUpload.disabled = false;
    els.uploadBtn.disabled = false;
    els.clearLineBtn.disabled = false;
    els.samplingIntervalInput.disabled = false;
    
    // Re-enable tab selectors
    els.tabSignalBtn.disabled = false;
    els.tabDirectionBtn.disabled = false;
    els.tabParkingBtn.disabled = false;
    els.tabTripleBtn.disabled = false;
    els.tabHelmetBtn.disabled = false;
}

// Query progress and current statistics
async function pollAnalysisProgress() {
    try {
        // Poll progress
        const progRes = await fetch("/progress");
        if (!progRes.ok) return;
        const progData = await progRes.json();
        
        const progressVal = progData.progress || 0;
        els.progressBarFill.style.width = `${progressVal}%`;
        els.progressBarText.textContent = `${progressVal}%`;
        
        // Refresh the live frame preview from in-memory endpoint if running
        if (progData.is_running && progressVal > 0) {
            els.videoFeed.src = `/current_frame?t=${Date.now()}`;
        }
        
        // Poll current stats
        const statsRes = await fetch("/stats");
        if (!statsRes.ok) return;
        const data = await statsRes.json();
        
        // Sync configs
        if (data.signal_state !== state.signalState) {
            state.signalState = data.signal_state;
            updateSignalUI();
        }
        
        // Update active mode display label based on backend synced value
        if (data.mode === "triple_riding") {
            els.statActiveMode.textContent = "Triple Rider";
        } else if (data.mode === "helmet") {
            els.statActiveMode.textContent = "Helmet Violation";
        } else if (data.mode === "parking") {
            els.statActiveMode.textContent = "No Parking";
        } else if (data.mode === "direction") {
            els.statActiveMode.textContent = "Wrong Way";
        } else {
            els.statActiveMode.textContent = "Traffic Signal";
        }
        
        // Update stats cards
        els.statTotalVehicles.textContent = data.stats.total_vehicles;
        els.statTotalViolations.textContent = data.stats.total_violations;
        
        // Update vehicle details table
        els.countCar.textContent = data.stats.vehicle_counts.car || 0;
        els.countMotorcycle.textContent = data.stats.vehicle_counts.motorcycle || 0;
        els.countBus.textContent = data.stats.vehicle_counts.bus || 0;
        els.countTruck.textContent = data.stats.vehicle_counts.truck || 0;
        els.countBicycle.textContent = data.stats.vehicle_counts.bicycle || 0;
        
        // Populate violation logs
        renderViolationsLog(data.violations);
        
        // Update status text feedback
        els.analysisStatsFeedback.textContent = `Progress: ${progressVal}% | Vehicles: ${data.stats.total_vehicles} | Violations: ${data.stats.total_violations}`;
        
        // If the backend indicates it finished processing by itself, trigger complete UI
        if (!progData.is_running && state.isStreamActive) {
            console.log("Video processing finished.");
            completeDetection();
        }
    } catch (e) {
        console.error("Progress/Stats polling failed:", e);
    }
}

// Render the violation history table rows
// Render the violation history table rows
function renderViolationsLog(violations) {
    renderTableRows(violations, els.violationsLogBody);
}

// Reset stats and clean folder on server
async function clearViolationsLog() {
    if (!confirm("Are you sure you want to clear all violation history and reset stats? This will delete all cropped evidence photos.")) {
        return;
    }
    
    try {
        const res = await fetch("/clear_violations", { method: "POST" });
        if (res.ok) {
            els.statTotalVehicles.textContent = "0";
            els.statTotalViolations.textContent = "0";
            els.countCar.textContent = "0";
            els.countMotorcycle.textContent = "0";
            els.countBus.textContent = "0";
            els.countTruck.textContent = "0";
            els.countBicycle.textContent = "0";
            
            els.violationsLogBody.innerHTML = `
                <tr>
                    <td colspan="11" class="empty-table-msg" style="text-align: center;">No violations recorded. System idle.</td>
                </tr>
            `;
            
            state.allViolations = [];
            if (state.typeChart) {
                state.typeChart.data.labels = [];
                state.typeChart.data.datasets[0].data = [];
                state.typeChart.update();
            }
            if (state.locationChart) {
                state.locationChart.data.labels = [];
                state.locationChart.data.datasets[0].data = [];
                state.locationChart.update();
            }
            
            // Also refresh analytics numbers
            els.anaTotalViolations.textContent = "0";
            els.anaFinesCollected.textContent = "₹0.00";
            els.anaFinesPending.textContent = "₹0.00";
            els.anaActiveDisputes.textContent = "0";
            els.anaViolationsLogBody.innerHTML = `
                <tr>
                    <td colspan="11" class="empty-table-msg" style="text-align: center;">No violations recorded. System idle.</td>
                </tr>
            `;
            
            // Reset query Inbox
            els.queryInboxList.innerHTML = `<div style="text-align: center; color: #777; font-style: italic; padding: 20px;">No dispute cases raised.</div>`;
            els.queryDetailPanel.style.display = "none";
            els.queryPlaceholderPanel.style.display = "flex";
            state.selectedQueryId = "";
            
            alert("Violation records and cropped images cleared successfully.");
        }
    } catch (e) {
        console.error("Clear violations log error:", e);
    }
}

// Lightbox Open handler
function openLightbox(cropUrl, id, timestamp, violationType, vehicleType, conf, licensePlate) {
    els.cropModalImg.src = cropUrl;
    els.modalTitle.textContent = `VIOLATION EVIDENCE: LOG ENTRY #${id}`;
    els.modalDetails.textContent = `VIOLATION: ${violationType} \nTIMESTAMP: ${timestamp} \nCLASSIFICATION: ${vehicleType.toUpperCase()} \nLICENSE PLATE: ${licensePlate} \nDETECTION CONFIDENCE: ${conf}%`;
    els.cropModal.style.display = "block";
}

/* --- SPA Tab Switching and View Loaders --- */

// Fetch database records
async function fetchDatabaseViolations() {
    try {
        const res = await fetch("/api/violations");
        if (res.ok) {
            state.allViolations = await res.json();
        } else {
            console.error("HTTP error fetching database violations");
        }
    } catch (e) {
        console.error("Error fetching database violations:", e);
    }
}

// Switch SPA tab view
async function switchMainTab(viewName) {
    // 1. Toggle Tab Styling
    els.navTabAnalytics.classList.remove("active");
    els.navTabControlPanel.classList.remove("active");
    els.navTabQueries.classList.remove("active");
    els.navTabInspector.classList.remove("active");
    
    // 2. Toggle View Visibility (Using inline styles to override default display: none)
    els.viewAnalytics.style.display = "none";
    els.viewControlPanel.style.display = "none";
    els.viewQueries.style.display = "none";
    els.viewInspector.style.display = "none";
    
    if (viewName === "analytics") {
        els.navTabAnalytics.classList.add("active");
        els.viewAnalytics.style.display = "block";
        await fetchDatabaseViolations();
        renderAnalyticsView();
    } else if (viewName === "control-panel") {
        els.navTabControlPanel.classList.add("active");
        els.viewControlPanel.style.display = "block";
    } else if (viewName === "queries") {
        els.navTabQueries.classList.add("active");
        els.viewQueries.style.display = "block";
        await fetchDatabaseViolations();
        renderDisputesView();
    } else if (viewName === "inspector") {
        els.navTabInspector.classList.add("active");
        els.viewInspector.style.display = "block";
    }
}

/* --- Analytics View Logic --- */

// Renders the Analytics stats, charts, and filter options
function renderAnalyticsView() {
    const violations = state.allViolations;
    
    // 1. Compute stats
    let totalViolations = violations.length;
    let finesCollected = 0.0;
    let finesPending = 0.0;
    let activeDisputes = 0;
    
    violations.forEach(v => {
        const amount = parseFloat(v.challan_amount) || 0.0;
        if (v.challan_status === "PAID") {
            finesCollected += amount;
        } else {
            finesPending += amount;
        }
        if (v.query_status !== "NONE") {
            activeDisputes++;
        }
    });
    
    els.anaTotalViolations.textContent = totalViolations;
    els.anaFinesCollected.textContent = `₹${finesCollected.toFixed(2)}`;
    els.anaFinesPending.textContent = `₹${finesPending.toFixed(2)}`;
    els.anaActiveDisputes.textContent = activeDisputes;
    
    // 2. Populate filters
    const currLocation = els.anaFilterLocation.value;
    const currType = els.anaFilterType.value;
    
    const uniqueLocations = [...new Set(violations.map(v => v.location).filter(Boolean))];
    const uniqueTypes = [...new Set(violations.map(v => v.violation_type).filter(Boolean))];
    
    els.anaFilterLocation.innerHTML = '<option value="">All Locations</option>';
    uniqueLocations.forEach(loc => {
        const opt = document.createElement("option");
        opt.value = loc;
        opt.textContent = loc;
        els.anaFilterLocation.appendChild(opt);
    });
    
    els.anaFilterType.innerHTML = '<option value="">All Types</option>';
    uniqueTypes.forEach(t => {
        const opt = document.createElement("option");
        opt.value = t;
        opt.textContent = t;
        els.anaFilterType.appendChild(opt);
    });
    
    if (uniqueLocations.includes(currLocation)) els.anaFilterLocation.value = currLocation;
    if (uniqueTypes.includes(currType)) els.anaFilterType.value = currType;
    
    // 3. Render charts
    updateAnalyticsCharts(violations);
    
    // 4. Render Table
    filterAnalytics();
}

// Re-computes and draws Chart.js graphics
function updateAnalyticsCharts(violations) {
    const typeCounts = {};
    violations.forEach(v => {
        const type = v.violation_type || "Unknown";
        typeCounts[type] = (typeCounts[type] || 0) + 1;
    });
    const typeLabels = Object.keys(typeCounts);
    const typeData = Object.values(typeCounts);
    
    const locCounts = {};
    violations.forEach(v => {
        const loc = v.location || "Unknown";
        locCounts[loc] = (locCounts[loc] || 0) + 1;
    });
    const locLabels = Object.keys(locCounts);
    const locData = Object.values(locCounts);
    
    const typeColors = ['#0b2f64', '#d4af37', '#c62828', '#2e7d32', '#d97706', '#3b82f6', '#10b981', '#6366f1'];
    
    // Types Doughnut
    if (state.typeChart) {
        state.typeChart.data.labels = typeLabels;
        state.typeChart.data.datasets[0].data = typeData;
        state.typeChart.data.datasets[0].backgroundColor = typeColors.slice(0, typeLabels.length);
        state.typeChart.update();
    } else {
        const ctxType = document.getElementById("chartViolationTypes").getContext("2d");
        state.typeChart = new Chart(ctxType, {
            type: 'doughnut',
            data: {
                labels: typeLabels,
                datasets: [{
                    data: typeData,
                    backgroundColor: typeColors.slice(0, typeLabels.length),
                    borderWidth: 1,
                    borderColor: '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: { boxWidth: 12, font: { size: 10 } }
                    }
                }
            }
        });
    }
    
    // Locations Bar
    if (state.locationChart) {
        state.locationChart.data.labels = locLabels;
        state.locationChart.data.datasets[0].data = locData;
        state.locationChart.update();
    } else {
        const ctxLoc = document.getElementById("chartLocations").getContext("2d");
        state.locationChart = new Chart(ctxLoc, {
            type: 'bar',
            data: {
                labels: locLabels,
                datasets: [{
                    label: 'Violations Count',
                    data: locData,
                    backgroundColor: '#0b2f64',
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, ticks: { stepSize: 1, font: { size: 9 } } },
                    x: { ticks: { font: { size: 9 } } }
                }
            }
        });
    }
}

// Handles filters on input/change events
function filterAnalytics() {
    const query = els.anaFilterSearch.value.trim().toLowerCase();
    const loc = els.anaFilterLocation.value;
    const type = els.anaFilterType.value;
    const status = els.anaFilterStatus.value;
    
    const filtered = state.allViolations.filter(v => {
        if (loc && v.location !== loc) return false;
        if (type && v.violation_type !== type) return false;
        if (status && v.challan_status !== status) return false;
        if (query) {
            const plateMatch = (v.license_plate || "").toLowerCase().includes(query);
            const idMatch = (v.violation_id || "").toLowerCase().includes(query);
            return plateMatch || idMatch;
        }
        return true;
    });
    
    renderTableRows(filtered, els.anaViolationsLogBody);
}

// Unified HTML rows builder for tables
function renderTableRows(violations, tbody) {
    if (!tbody) return;
    if (violations.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="11" class="empty-table-msg" style="text-align: center;">No matching violation logs found.</td>
            </tr>
        `;
        return;
    }
    
    let html = "";
    violations.forEach(v => {
        let cropUrl = v.crop_url || "";
        if (cropUrl.startsWith("/")) {
            cropUrl = CONFIG.BACKEND_URL + cropUrl;
        }
        const vType = v.violation_type ? v.violation_type.replace(/'/g, "\\'") : "";
        const vehType = v.vehicle_type ? v.vehicle_type.replace(/'/g, "\\'") : "";
        const timestamp = v.timestamp ? v.timestamp.replace(/'/g, "\\'") : "";
        const plate = v.license_plate ? v.license_plate.replace(/'/g, "\\'") : "NOT DETECTED";
        
        const locDisplay = v.location && v.video_filename ? `${v.location} (${v.video_filename})` : (v.location || v.video_filename || "N/A");
        const statusBadgeClass = v.challan_status === "PAID" ? "badge-paid" : "badge-pending";
        const statusText = v.challan_status || "PENDING";
        const challanNo = v.challan_number || "N/A";
        const detailUrl = v.detail_url || `#`;
        
        html += `
            <tr>
                <td style="font-weight: bold; text-align: center;">${v.id}</td>
                <td><span class="violation-tag" style="color: #c62828; font-weight: bold; font-size: 11px;">${v.violation_type}</span></td>
                <td style="font-size: 11px;">${locDisplay}</td>
                <td style="font-family: monospace;">${v.timestamp}</td>
                <td><span style="text-transform: uppercase; font-weight: bold;">${v.vehicle_type}</span></td>
                <td style="font-family: monospace; font-weight: bold; color: #1a237e;">${v.license_plate || 'NOT DETECTED'}</td>
                <td style="font-family: monospace;">${v.confidence}%</td>
                <td style="font-family: monospace; font-weight: bold;">${challanNo}</td>
                <td style="text-align: center;">
                    <span class="${statusBadgeClass}">${statusText}</span>
                </td>
                <td style="text-align: center;">
                    <img class="violation-thumbnail" src="${cropUrl}" alt="Crop of vehicle #${v.id}" 
                         onclick="openLightbox('${cropUrl}', ${v.id}, '${timestamp}', '${vType}', '${vehType}', ${v.confidence}, '${plate}')"
                         style="width: 55px; height: 55px; object-fit: cover; border: 1px solid #777; cursor: pointer; border-radius: 4px; display: inline-block;">
                </td>
                <td style="text-align: center;">
                    <a class="detail-link-btn" href="${detailUrl}" target="_blank">View Details</a>
                </td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
}

/* --- Dispute Queries inbox logic --- */

// Populate dispute sidebar list
function renderDisputesView() {
    const disputes = state.allViolations.filter(v => v.query_status && v.query_status !== "NONE");
    
    if (disputes.length === 0) {
        els.queryInboxList.innerHTML = `<div style="text-align: center; color: #777; font-style: italic; padding: 20px;">No dispute cases raised.</div>`;
        els.queryDetailPanel.style.display = "none";
        els.queryPlaceholderPanel.style.display = "flex";
        state.selectedQueryId = "";
        return;
    }
    
    let html = "";
    disputes.forEach(v => {
        const activeClass = v.violation_id === state.selectedQueryId ? "active" : "";
        const badgeClass = v.query_status === "RESOLVED" ? "badge-resolved" : "badge-under-review";
        const statusText = v.query_status === "RESOLVED" ? "RESOLVED" : "UNDER REVIEW";
        
        html += `
            <div class="query-card ${activeClass}" onclick="selectDisputeCase('${v.violation_id}')">
                <div class="card-title">${v.violation_id}</div>
                <div class="card-meta">Challan: ${v.challan_number}</div>
                <div class="card-meta">Plate: ${v.license_plate || 'N/A'} | Time: ${v.timestamp}</div>
                <span class="badge ${badgeClass}">${statusText}</span>
            </div>
        `;
    });
    
    els.queryInboxList.innerHTML = html;
    
    // Auto select first dispute if none selected
    if (!state.selectedQueryId && disputes.length > 0) {
        selectDisputeCase(disputes[0].violation_id);
    } else if (state.selectedQueryId) {
        // Refresh details for active case
        const found = disputes.find(d => d.violation_id === state.selectedQueryId);
        if (found) selectDisputeCase(found.violation_id);
    }
}

// Select query card and load details + chat bubbles
function selectDisputeCase(violationId) {
    state.selectedQueryId = violationId;
    
    // Re-highlight cards in DOM
    const cards = els.queryInboxList.querySelectorAll(".query-card");
    cards.forEach(card => {
        const titleEl = card.querySelector(".card-title");
        if (titleEl && titleEl.textContent === violationId) {
            card.classList.add("active");
        } else {
            card.classList.remove("active");
        }
    });
    
    const v = state.allViolations.find(item => item.violation_id === violationId);
    if (!v) return;
    
    els.queryPlaceholderPanel.style.display = "none";
    els.queryDetailPanel.style.display = "flex";
    
    // Fill metadata
    els.queryDetailTitle.textContent = `DISPUTE: ${v.violation_id}`;
    els.queryDetailSub.textContent = `Challan No: ${v.challan_number} | Location: ${v.location || 'N/A'}`;
    
    const badgeClass = v.query_status === "RESOLVED" ? "badge-resolved" : "badge-under-review";
    els.queryDetailBadge.className = `badge ${badgeClass}`;
    els.queryDetailBadge.textContent = v.query_status === "RESOLVED" ? "RESOLVED" : "UNDER REVIEW";
    
    els.queryDetailName.textContent = v.violator_name || "Rajesh Kumar";
    els.queryDetailMobile.textContent = v.violator_mobile || "+91 98765 43210";
    els.queryDetailVehicle.textContent = (v.vehicle_type || "MOTORCYCLE").toUpperCase();
    els.queryDetailPlate.textContent = v.license_plate || "NOT DETECTED";
    let cropUrl = v.crop_url || "";
    if (cropUrl.startsWith("/")) {
        cropUrl = CONFIG.BACKEND_URL + cropUrl;
    }
    els.queryDetailImg.src = cropUrl;
    
    // Render Chat
    let chatHistory = [];
    try {
        chatHistory = JSON.parse(v.query_chat || "[]");
    } catch(e) {
        chatHistory = [];
    }
    
    let chatHtml = "";
    chatHistory.forEach(m => {
        const senderClass = m.sender === "authority" ? "authority" : "user";
        chatHtml += `
            <div class="chat-msg ${senderClass}">
                <div>${m.message}</div>
                <div class="chat-msg-time">${m.timestamp || ''}</div>
            </div>
        `;
    });
    
    els.queryAdminChatBox.innerHTML = chatHtml;
    els.queryAdminChatBox.scrollTop = els.queryAdminChatBox.scrollHeight;
    
    // Toggle active inputs if case is already resolved
    const isResolved = v.query_status === "RESOLVED";
    els.queryAdminInput.disabled = isResolved;
    els.queryAdminSendBtn.disabled = isResolved;
    els.queryAdminDismissBtn.disabled = isResolved;
    els.queryAdminUpholdBtn.disabled = isResolved;
}

// Send admin texting message reply
async function sendAdminQueryReply() {
    const text = els.queryAdminInput.value.trim();
    if (!text || !state.selectedQueryId) return;
    
    els.queryAdminSendBtn.disabled = true;
    els.queryAdminInput.disabled = true;
    
    try {
        const res = await fetch(`/api/violation/${state.selectedQueryId}/reply`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text, status: "UNDER_REVIEW" })
        });
        
        if (res.ok) {
            els.queryAdminInput.value = "";
            await fetchDatabaseViolations();
            renderDisputesView();
        } else {
            alert("Failed to send reply. Please try again.");
        }
    } catch(e) {
        console.error(e);
        alert("Error sending message to server.");
    } finally {
        els.queryAdminSendBtn.disabled = false;
        els.queryAdminInput.disabled = false;
        els.queryAdminInput.focus();
    }
}

// Waive Challan (Approve citizen dispute)
async function waiveChallan() {
    if (!state.selectedQueryId) return;
    if (!confirm("Are you sure you want to WAIVE this challan? The citizen's challan status will be updated to PAID and dispute marked as RESOLVED.")) return;
    
    try {
        // 1. Reply to chat & resolve
        await fetch(`/api/violation/${state.selectedQueryId}/reply`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: "Your dispute has been reviewed. The traffic authority has waived this challan. Case resolved successfully.",
                status: "RESOLVED"
            })
        });
        
        // 2. Mark challan as paid (Waived)
        await fetch(`/violation/${state.selectedQueryId}/pay`, { method: "POST" });
        
        await fetchDatabaseViolations();
        renderDisputesView();
    } catch(e) {
        console.error(e);
        alert("Error waiving challan.");
    }
}

// Reject Dispute (Keep challan active)
async function rejectDispute() {
    if (!state.selectedQueryId) return;
    if (!confirm("Are you sure you want to REJECT this dispute? The challan will remain pending and dispute marked as RESOLVED.")) return;
    
    try {
        await fetch(`/api/violation/${state.selectedQueryId}/reply`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: "Your dispute has been reviewed. The evidence clearly indicates a traffic signal violation. The dispute has been rejected and the challan remains active.",
                status: "RESOLVED"
            })
        });
        
        await fetchDatabaseViolations();
        renderDisputesView();
    } catch(e) {
        console.error(e);
        alert("Error rejecting dispute.");
    }
}

/* --- Video Inspector Logic --- */

// Search violation ID and load raw video
async function searchInspectionRecord() {
    const query = els.inspectorSearchId.value.trim().toUpperCase();
    if (!query) return;
    
    await fetchDatabaseViolations();
    const found = state.allViolations.find(v => (v.violation_id || "").toUpperCase() === query);
    
    if (found) {
        state.inspectorRecord = found;
        els.inspectorErrorPanel.style.display = "none";
        els.inspectorContentPanel.style.display = "grid";
        
        // Populate report fields
        els.insReportId.textContent = found.violation_id;
        els.insReportType.textContent = found.violation_type;
        els.insReportLocation.textContent = found.location || "N/A";
        els.insReportName.textContent = found.violator_name || "Rajesh Kumar";
        els.insReportVideo.textContent = found.video_filename || "N/A";
        els.insReportTimestamp.textContent = found.timestamp || "N/A";
        els.insReportPlate.textContent = found.license_plate || "NOT DETECTED";
        let cropUrl = found.crop_url || "";
        if (cropUrl.startsWith("/")) {
            cropUrl = CONFIG.BACKEND_URL + cropUrl;
        }
        els.insReportCropImg.src = cropUrl;
        
        // Load raw video
        const videoUrl = `${CONFIG.BACKEND_URL}/videos_raw/${encodeURIComponent(found.video_filename)}`;
        els.inspectorVideoPlayer.src = videoUrl;
        els.inspectorVideoPlayer.load();
        
        // Auto jump when video is ready
        els.inspectorVideoPlayer.onloadedmetadata = () => {
            jumpToInspectorTime();
        };
    } else {
        state.inspectorRecord = null;
        els.inspectorContentPanel.style.display = "none";
        els.inspectorErrorPanel.style.display = "block";
    }
}

// Seek video to violation timestamp
function jumpToInspectorTime() {
    if (!state.inspectorRecord || !els.inspectorVideoPlayer.src) return;
    
    const seconds = parseTimeToSeconds(state.inspectorRecord.timestamp);
    els.inspectorVideoPlayer.currentTime = seconds;
    els.inspectorVideoPlayer.play();
}

// Parse string MM:SS or HH:MM:SS to seconds
function parseTimeToSeconds(timeStr) {
    if (!timeStr) return 0;
    if (!isNaN(timeStr)) return parseFloat(timeStr);
    const parts = timeStr.split(':').map(Number);
    if (parts.length === 3) {
        return parts[0] * 3600 + parts[1] * 60 + parts[2];
    } else if (parts.length === 2) {
        return parts[0] * 60 + parts[1];
    }
    return 0;
}

// Run initial execution on load
window.addEventListener("DOMContentLoaded", init);
