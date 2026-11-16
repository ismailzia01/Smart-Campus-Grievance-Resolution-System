"""
Smart Campus Grievance & Resolution System
Application entry point.
"""

import os
from backend import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    debug_env = os.environ.get('FLASK_DEBUG', 'false').lower()
    debug_mode = debug_env in ('true', '1', 'yes', 'on')
    app.run(debug=debug_mode, port=port)
