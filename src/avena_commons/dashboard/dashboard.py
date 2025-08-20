import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from avena_commons.event_listener.event import Event
from avena_commons.event_listener.event_listener import EventListener
from avena_commons.util.logger import MessageLogger, debug, error
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from flask import Flask, jsonify, render_template


class Dashboard(EventListener):
    def __init__(
        self,
        name: str,
        port: int,
        address: str,
        web_port: int = None,  # Dodatkowy port dla Flask web interface
        message_logger: MessageLogger | None = None,
        do_not_load_state: bool = True,
    ):
        self._message_logger = message_logger
        self._service_status = {}  # Cache dla statusów serwisów
        self._web_port = web_port or (port + 1000)  # Domyślnie API port + 1000
        self._flask_app = None
        self._flask_server = None
        self._last_event_timestamps = {}  # Timestamp ostatniego eventu dla każdego serwisu

        try:
            super().__init__(
                name=name,
                port=port,
                address=address,
                message_logger=self._message_logger,
                do_not_load_state=True,
            )
            debug(
                f"konfiguracja: {self._configuration}",
            )

            # Dodaj API endpoints do FastAPI (zachowujemy dla JSON API)
            self._setup_api_routes()

            # Stwórz Flask app dla web interface
            self._setup_flask_app()

        except Exception as e:
            error(f"Initialisation error: {e}", message_logger=self._message_logger)

    def _setup_api_routes(self):
        """Konfiguruje FastAPI endpoints dla JSON API"""

        @self.app.get("/api/dashboard/status")
        async def get_system_status():
            """API endpoint zwracający status wszystkich serwisów"""
            return JSONResponse(self._get_system_status())

        @self.app.get("/api/dashboard/service/{service_name}")
        async def get_service_status(service_name: str):
            """API endpoint dla konkretnego serwisu"""
            status = self._get_system_status()
            if service_name in status:
                return JSONResponse(status[service_name])
            raise HTTPException(status_code=404, detail="Service not found")

        @self.app.get("/api/dashboard/health")
        async def health_check():
            """Health check endpoint"""
            status = self._get_system_status()
            online_services = [s for s in status.values() if s.get("online", False)]

            return JSONResponse(
                {
                    "status": "healthy"
                    if len(online_services) == len(status)
                    else "degraded",
                    "timestamp": datetime.now().isoformat(),
                    "services": {
                        "total": len(status),
                        "online": len(online_services),
                        "offline": len(status) - len(online_services),
                    },
                    "uptime_seconds": (
                        datetime.now() - self._start_time
                    ).total_seconds()
                    if hasattr(self, "_start_time")
                    else 0,
                }
            )

    def _setup_flask_app(self):
        """Konfiguruje Flask app dla web interface z debug informacjami"""
        # Znajdź ścieżkę do templates i static - BEZWZGLĘDNĄ
        current_dir = Path.cwd()
        dashboard_dir = current_dir / "src" / "avena_commons" / "dashboard"
        template_folder = dashboard_dir / "templates"
        static_folder = dashboard_dir / "static"

        # Sprawdź czy foldery istnieją
        debug(
            f"Current working directory: {current_dir}",
            message_logger=self._message_logger,
        )
        debug(
            f"Dashboard directory: {dashboard_dir}", message_logger=self._message_logger
        )
        debug(
            f"Template folder: {template_folder}", message_logger=self._message_logger
        )
        debug(
            f"Template folder exists: {template_folder.exists()}",
            message_logger=self._message_logger,
        )
        debug(
            f"Static folder exists: {static_folder.exists()}",
            message_logger=self._message_logger,
        )

        if template_folder.exists():
            template_files = list(template_folder.glob("*"))
            debug(
                f"Template files: {template_files}", message_logger=self._message_logger
            )

        if not template_folder.exists():
            error(
                f"Template folder not found: {template_folder}",
                message_logger=self._message_logger,
            )
            # Spróbuj alternatywnej ścieżki
            alt_dashboard_dir = Path(__file__).parent
            alt_template_folder = alt_dashboard_dir / "templates"
            debug(
                f"Trying alternative path: {alt_template_folder}",
                message_logger=self._message_logger,
            )
            if alt_template_folder.exists():
                template_folder = alt_template_folder
                static_folder = alt_dashboard_dir / "static"
                debug(
                    f"Using alternative template folder: {template_folder}",
                    message_logger=self._message_logger,
                )
            else:
                error(
                    f"Alternative template folder also not found: {alt_template_folder}",
                    message_logger=self._message_logger,
                )
                return

        self._flask_app = Flask(
            __name__,
            template_folder=str(template_folder.absolute()),
            static_folder=str(static_folder.absolute())
            if static_folder.exists()
            else None,
            static_url_path="/dashboard/static",
        )

        # Error handler
        @self._flask_app.errorhandler(500)
        def internal_error(error_obj):
            import traceback

            tb = traceback.format_exc()
            error(f"Flask 500 error: {tb}", message_logger=self._message_logger)
            return (
                f"""
            <h1>Internal Server Error</h1>
            <p>Dashboard error: {error_obj}</p>
            <pre>{tb}</pre>
            """,
                500,
            )

        # Root route
        @self._flask_app.route("/")
        def index():
            """Przekierowanie z root na dashboard"""
            from flask import redirect, url_for

            try:
                return redirect(url_for("dashboard_home"))
            except:
                return '<h1>Dashboard</h1><a href="/dashboard">Go to Dashboard</a> | <a href="/test">Test Page</a>'

        # Test route
        @self._flask_app.route("/test")
        def test():
            """Test endpoint"""
            return f"""
            <h1>Dashboard Test</h1>
            <p>Flask app działa!</p>
            <p>Template folder: {template_folder}</p>
            <p>Template folder exists: {template_folder.exists()}</p>
            <p>Static folder: {static_folder}</p>
            <p>API Port: {getattr(self, "_EventListener__port", "unknown")}</p>
            <p>Dashboard Name: {getattr(self, "_EventListener__name", "unknown")}</p>
            <p>Template files: {list(template_folder.glob("*")) if template_folder.exists() else "N/A"}</p>
            <hr>
            <a href="/dashboard">Idź do dashboard</a> | 
            <a href="/simple">Simple dashboard</a> |
            <a href="/dashboard/data">JSON data</a>
            """

        # Simple dashboard bez templates
        @self._flask_app.route("/simple")
        def simple_dashboard():
            """Simple dashboard bez templates"""
            try:
                services = self._get_system_status()
                html = """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Simple Dashboard</title>
                    <meta charset="UTF-8">
                    <style>
                        body { font-family: Arial, sans-serif; margin: 20px; }
                        .service { border: 1px solid #ccc; margin: 10px 0; padding: 15px; border-radius: 5px; }
                        .online { background-color: #d4edda; }
                        .offline { background-color: #f8d7da; }
                    </style>
                </head>
                <body>
                    <h1>Dashboard - Status Serwisów</h1>
                """

                if not services:
                    html += "<p>Brak skonfigurowanych serwisów</p>"
                else:
                    for name, service in services.items():
                        status_class = (
                            "online" if service["status"] == "connected" else "offline"
                        )

                        html += f"""
                        <div class="service {status_class}">
                            <h3>{name}</h3>
                            <p><strong>Status:</strong> {service["status"]}</p>
                            <p><strong>Online:</strong> {"Tak" if service["online"] else "Nie"}</p>
                            <p><strong>Adres:</strong> {service["address"]}</p>
                            {f"<p><strong>Ostatnia odpowiedź:</strong> {service['last_response']}</p>" if service.get("last_response") else ""}
                            {f"<p><strong>Sekundy od ostatniego eventu:</strong> {service['seconds_since_last_event']:.1f}s</p>" if service.get("seconds_since_last_event") is not None else ""}
                        </div>
                        """

                html += """
                    <hr>
                    <p><a href="/test">Test page</a> | <a href="/dashboard/data">JSON API</a></p>
                    <script>
                        setTimeout(() => location.reload(), 5000);
                    </script>
                </body>
                </html>
                """
                return html
            except Exception as e:
                return f"Error: {e}<br><pre>{traceback.format_exc()}</pre>"

        # Flask routes z template
        @self._flask_app.route("/dashboard")
        def dashboard_home():
            """Główna strona dashboardu"""
            try:
                debug(
                    "Attempting to render dashboard template",
                    message_logger=self._message_logger,
                )

                # Sprawdź dostępność danych
                api_port = getattr(self, "_EventListener__port", 8080)
                dashboard_name = getattr(
                    self, "_EventListener__name", "Unknown Dashboard"
                )

                debug(
                    f"Dashboard params: api_port={api_port}, name={dashboard_name}",
                    message_logger=self._message_logger,
                )

                # Sprawdź czy template istnieje
                template_path = template_folder / "dashboard.html"
                if not template_path.exists():
                    error(
                        f"Template file not found: {template_path}",
                        message_logger=self._message_logger,
                    )
                    return (
                        f"""
                    <h1>Template Error</h1>
                    <p>Template file not found: {template_path}</p>
                    <p>Available templates: {list(template_folder.glob("*")) if template_folder.exists() else "None"}</p>
                    <a href="/simple">Use simple dashboard instead</a>
                    """,
                        404,
                    )

                return render_template(
                    "dashboard.html",
                    api_port=api_port,
                    dashboard_name=dashboard_name,
                )

            except Exception as e:
                error(
                    f"Dashboard rendering error: {e}",
                    message_logger=self._message_logger,
                )
                import traceback

                return (
                    f"""
                <h1>Dashboard Error</h1>
                <p>Error: {e}</p>
                <pre>{traceback.format_exc()}</pre>
                <p><a href="/simple">Use simple dashboard instead</a></p>
                """,
                    500,
                )

        # Dodaj globalne CORS middleware dla wszystkich route'ów Flask
        @self._flask_app.after_request
        def after_request(response):
            response.headers.add("Access-Control-Allow-Origin", "*")
            response.headers.add(
                "Access-Control-Allow-Headers",
                "Content-Type,Authorization,X-Requested-With",
            )
            response.headers.add(
                "Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS"
            )
            response.headers.add("Access-Control-Allow-Credentials", "true")
            return response

        # Obsługuj OPTIONS preflight requests
        @self._flask_app.route("/dashboard/data", methods=["OPTIONS"])
        def dashboard_data_options():
            """CORS preflight handler"""
            response = jsonify({})
            response.headers.add("Access-Control-Allow-Origin", "*")
            response.headers.add(
                "Access-Control-Allow-Headers",
                "Content-Type,Authorization,X-Requested-With",
            )
            response.headers.add(
                "Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS"
            )
            return response

        @self._flask_app.route("/dashboard/data")
        def dashboard_data():
            """Flask endpoint dla danych (alternatywa do FastAPI)"""
            try:
                data = self._get_system_status()
                print(f"🌐 FLASK /dashboard/data returning: {len(data)} services")
                # Zwróć JSON z danymi (CORS już dodane globalnie)
                return jsonify(data)
            except Exception as e:
                error(f"Dashboard data error: {e}", message_logger=self._message_logger)
                return jsonify({"error": str(e)}), 500

    def start_web_server(self):
        """Uruchamia Flask web server w osobnym wątku"""
        if self._flask_app:

            def run_flask():
                try:
                    debug(
                        f"Starting Flask web server on 0.0.0.0:{self._web_port}",
                        message_logger=self._message_logger,
                    )

                    self._flask_app.run(
                        host="0.0.0.0",
                        port=self._web_port,
                        debug=False,
                        use_reloader=False,
                        threaded=True,
                    )
                except Exception as e:
                    error(
                        f"Flask server error: {e}", message_logger=self._message_logger
                    )

            flask_thread = threading.Thread(target=run_flask, daemon=True)
            flask_thread.start()

            debug(
                f"Flask web server started on port {self._web_port}",
                message_logger=self._message_logger,
            )

    def _get_system_status(self) -> Dict[str, Any]:
        """Zwraca statusy wszystkich serwisów na podstawie ostatnich eventów (5s timeout)"""
        status = {}
        current_time = datetime.now()

        # Inicjalizuj wszystkich klientów z konfiguracji
        if "clients" in self._configuration:
            for client_name, client_config in self._configuration["clients"].items():
                # Sprawdź czy otrzymano event w ciągu ostatnich 5 sekund
                last_event_time = self._last_event_timestamps.get(client_name)
                is_online = False
                seconds_since_last_event = None

                if last_event_time:
                    seconds_since_last_event = (
                        current_time - last_event_time
                    ).total_seconds()
                    is_online = seconds_since_last_event <= 5.0

                # Pobierz dane ze state'u
                service_state_data = self._state.get(client_name, {})

                status[client_name] = {
                    "online": is_online,
                    "status": "connected" if is_online else "offline",
                    "last_response": last_event_time.isoformat()
                    if last_event_time
                    else None,
                    "seconds_since_last_event": seconds_since_last_event,
                    "data": service_state_data,
                    "address": f"{client_config.get('address', 'unknown')}:{client_config.get('port', 'unknown')}",
                }

        return status

    async def _analyze_event(self, event: Event) -> bool:
        match event.event_type:
            case "CMD_GET_STATE":
                if event.result is not None:
                    # Event ma result - usuń go z processing
                    self._find_and_remove_processing_event(event)
                    debug(
                        f"Received state from {event.source}: {event.result.result}",
                        message_logger=self._message_logger,
                    )
                    # Zapisz timestamp otrzymania eventu dla tego serwisu
                    self._last_event_timestamps[event.source] = datetime.now()
                    # Zapisz dane ze state'u
                    self._state[event.source] = event.data if event.data else {}
                    debug(
                        f"Saved state for {event.source}: {len(self._state[event.source])} keys",
                        message_logger=self._message_logger,
                    )
                    print(f"🌐 STATE: {self._state}")
            case _:
                # Dla wszystkich innych eventów też zapisuj timestamp
                if hasattr(event, "source") and event.source:
                    self._last_event_timestamps[event.source] = datetime.now()
        return True

    async def _check_local_data(self):  # MARK: CHECK LOCAL DATA
        """Rozszerzona wersja sprawdzania danych lokalnych"""
        # POPRAWKA: używamy _configuration zamiast _default_configuration
        if not hasattr(self, "_configuration") or "clients" not in self._configuration:
            debug(
                "No clients configured for monitoring",
                message_logger=self._message_logger,
            )
            return

        for key, client in self._configuration["clients"].items():
            client_port = client["port"]
            client_address = client["address"]

            # Sprawdź czy już nie ma pendującego zapytania dla tego klienta
            pending_events = [
                e
                for e in self._processing_events_dict.values()
                if e.destination == key and e.event_type == "CMD_GET_STATE"
            ]

            if not pending_events:
                event = await self._event(
                    destination=key,
                    destination_address=client_address,
                    destination_port=client_port,
                    event_type="CMD_GET_STATE",
                    data={},
                    to_be_processed=False,
                )
                self._add_to_processing(event)
                debug(
                    f"Sent CMD_GET_STATE to {key} at {client_address}:{client_port}",
                    message_logger=self._message_logger,
                )

    def start(self):
        """Override start method to also start Flask server"""
        # Uruchom web server
        self.start_web_server()
        # Uruchom główny EventListener
        super().start()

    def _clear_before_shutdown(self):
        __logger = self._message_logger  # Zapisz referencję jeśli potrzebna
        # Ustaw na None aby inne wątki nie próbowały używać
        self._message_logger = None
