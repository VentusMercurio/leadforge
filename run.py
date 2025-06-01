# leadforge_backend/run.py
from app import create_app # Import the factory function

app = create_app() # Create the app instance

if __name__ == '__main__':
    # Use app.config for debug and port if set there, otherwise default
    debug_mode = app.config.get('FLASK_DEBUG', False)
    port_num = app.config.get('FLASK_RUN_PORT', 5003) # Example: add FLASK_RUN_PORT to .env if you want to config port there
    app.run(debug=debug_mode, host='0.0.0.0', port=port_num)