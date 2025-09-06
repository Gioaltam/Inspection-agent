#!/usr/bin/env python3
"""
Main entry point for CheckMyRental app on Replit
"""
import os
import sys
import subprocess

def setup_environment():
    """Set up the environment and install dependencies"""
    print("Setting up CheckMyRental app...")
    
    # Install dependencies
    print("Installing dependencies...")
    req_file = "requirements-replit.txt" if os.path.exists("requirements-replit.txt") else "requirements.txt"
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_file])
    
    # Create necessary directories
    os.makedirs("static", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    os.makedirs(".cache", exist_ok=True)
    
    print("Setup complete!")

def run_server():
    """Run the FastAPI server"""
    print("Starting CheckMyRental server...")
    
    # Import here to ensure dependencies are installed first
    import uvicorn
    from simple_portal_server import app
    
    # Get port from environment or use default
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"
    
    print(f"Server starting on {host}:{port}")
    print(f"Access your app at: https://{os.environ.get('REPL_SLUG', 'your-app')}.{os.environ.get('REPL_OWNER', 'username')}.repl.co")
    
    # Run the server
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    # Check if dependencies are installed
    try:
        import fastapi
        import uvicorn
    except ImportError:
        setup_environment()
    
    # Run the server
    run_server()