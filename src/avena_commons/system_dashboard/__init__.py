"""
#### System Dashboard

Internetowy dashboard systemu oparty na Flask do monitorowania zasobów systemowych w czasie rzeczywistym.

#### Główne komponenty:
- `app`: Serwer Flask z endpointami do monitorowania systemu i uwierzytelniania
- `system_status`: Moduł zbierający informacje o zasobach systemowych

#### Funkcjonalności:
- Monitorowanie CPU, pamięci, dysku i sieci
- Interfejs webowy z dynamicznym odświeżaniem
- Prostą uwierzytelnianie użytkownika
- Endpoint JSON API do pobierania danych systemowych

#### Użycie:
```python
from avena_commons.system_dashboard import run_app
run_app()  # Uruchamia serwer Flask na porcie 5000
```
"""

from .app import run_app as run_app
