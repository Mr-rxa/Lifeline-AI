from flask import Flask, render_template
from config import Config
from extensions import db, bcrypt, jwt
from routes import register_routes
import os

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize Flask extensions
    db.init_app(app)
    
    # Enable WAL mode for SQLite to prevent database locks during high concurrency
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    bcrypt.init_app(app)
    jwt.init_app(app)

    # Register Blueprints
    register_routes(app)

    # Serve the main Single Page Application
    @app.route('/')
    def index():
        return render_template('index.html')
        
    @app.route('/driver')
    def driver_mode():
        return render_template('driver.html')

    @app.route('/citizen')
    def citizen_mode():
        return render_template('citizen.html')

    @app.route('/hospital')
    def hospital_mode():
        return render_template('hospital.html')

    # Create tables on startup
    with app.app_context():
        db.create_all()
        # Ensure we have some base data
        from init_db import init_hospitals, init_admin, init_fleet_and_demo_data
        init_hospitals()
        init_admin()
        init_fleet_and_demo_data()

    return app

if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
