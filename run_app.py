import os
import sys

# Ensure parent folder of web_app is in the python path so 'web_app' package is importable
web_app_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(web_app_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    import uvicorn
except ImportError:
    print("Error: 'uvicorn' is not installed. Please run 'pip install -r requirements.txt' first.")
    sys.exit(1)

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 8000))
    
    # If on Render or external port is specified, bind to all interfaces
    if os.getenv("RENDER") or os.getenv("PORT"):
        host = "0.0.0.0"
        
    print("==================================================================")
    print("  TRAFFIC SIGNAL VIOLATION DETECTION SYSTEM - MONITOR CONSOLE")
    print("==================================================================")
    print(f"Starting FastAPI Application Server on {host}:{port}...")
    print("==================================================================")
    
    # Disabling hot-reload in production environments
    reload = not (os.getenv("RENDER") or os.getenv("PORT"))
    
    # Run uvicorn server
    uvicorn.run("backend.main:app", host=host, port=port, reload=reload)
