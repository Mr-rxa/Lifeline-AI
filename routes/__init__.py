def register_routes(app):
    from .auth import auth_bp
    from .ambulances import amb_bp
    from .hospitals import hosp_bp
    from .incidents import inc_bp
    from .tracking import track_bp
    from .analytics import stats_bp
    from .users import users_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(amb_bp, url_prefix='/api/ambulances')
    app.register_blueprint(hosp_bp, url_prefix='/api/hospitals')
    app.register_blueprint(inc_bp, url_prefix='/api/incidents')
    app.register_blueprint(track_bp, url_prefix='/api/tracking')
    app.register_blueprint(stats_bp, url_prefix='/api/analytics')
    app.register_blueprint(users_bp, url_prefix='/api/users')
