# Plan Implementacji Orchestratora - Szczegółowy Breakdown

## Struktura Projektu

```
src/avena_commons/orchestrator/
├── __init__.py
├── orchestrator.py                    # Główna klasa Orchestrator
├── models/
│   ├── __init__.py
│   ├── component.py                   # Model komponentu
│   ├── scenario.py                    # Modele scenariuszy
│   ├── states.py                      # FSM states definitions
│   └── events.py                      # Event types
├── core/
│   ├── __init__.py
│   ├── component_registry.py          # Rejestr komponentów
│   ├── health_monitor.py              # Health checking
│   ├── fsm_manager.py                 # Finite State Machine
│   └── dependency_manager.py          # Zarządzanie zależnościami
├── scenarios/
│   ├── __init__.py
│   ├── scenario_loader.py             # Ładowanie YAML
│   ├── scenario_executor.py           # Wykonywanie scenariuszy
│   ├── action_handlers/
│   │   ├── __init__.py
│   │   ├── base.py                    # Bazowy handler
│   │   ├── command_actions.py         # send_command, wait_for_state
│   │   ├── logging_actions.py         # log_event
│   │   └── notification_actions.py    # send_notification
│   └── validators.py                  # Walidacja scenariuszy
├── monitoring/
│   ├── __init__.py
│   ├── metrics_collector.py           # Zbieranie metryk
│   ├── trend_analyzer.py              # Analiza trendów
│   ├── alerting.py                    # System alertów
│   └── dashboard_data_provider.py     # Dane dla dashboard
├── redundancy/                        # Poziom 2+
│   ├── __init__.py
│   ├── failover_manager.py
│   ├── heartbeat_monitor.py
│   ├── consensus_manager.py
│   └── state_replication.py
├── security/                          # Poziom 2+
│   ├── __init__.py
│   ├── auth_manager.py
│   ├── token_validator.py
│   └── audit_logger.py
└── utils/
    ├── __init__.py
    ├── config_loader.py               # Ładowanie konfiguracji
    ├── template_engine.py             # Template processing ({{ }})
    └── retry_mechanisms.py            # Retry logic
```

## Poziom 0: Foundation - Implementacja Krok po Kroku

### Krok 1: Podstawowe Modele (models/)

**models/states.py:**
```python
from enum import Enum
from typing import Set, Dict, Optional

class ComponentState(Enum):
    UNKNOWN = -1
    READY = 0
    INITIALIZING = 1
    INIT_COMPLETE = 2
    STARTED = 3
    STOPPING = 4
    STOPPED = 5
    FAULT = 6

class ComponentStatus(Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    UNRESPONSIVE = "UNRESPONSIVE"
    DEGRADED = "DEGRADED"

# FSM transition rules
FSM_TRANSITIONS: Dict[ComponentState, Set[ComponentState]] = {
    ComponentState.UNKNOWN: {ComponentState.READY},
    ComponentState.READY: {ComponentState.INITIALIZING},
    ComponentState.INITIALIZING: {ComponentState.INIT_COMPLETE, ComponentState.FAULT},
    ComponentState.INIT_COMPLETE: {ComponentState.STARTED},
    ComponentState.STARTED: {ComponentState.STOPPING, ComponentState.FAULT},
    ComponentState.STOPPING: {ComponentState.STOPPED},
    ComponentState.STOPPED: {ComponentState.INITIALIZING},
    ComponentState.FAULT: {ComponentState.READY}
}

def can_transition(from_state: ComponentState, to_state: ComponentState) -> bool:
    """Sprawdza czy przejście między stanami jest dozwolone"""
    return to_state in FSM_TRANSITIONS.get(from_state, set())
```

**models/component.py:**
```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from .states import ComponentState, ComponentStatus

@dataclass
class ComponentInfo:
    """Informacje o zarejestrowanym komponencie"""
    id: str
    name: str
    address: str
    port: int
    groups: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Runtime state
    state: ComponentState = ComponentState.UNKNOWN
    status: ComponentStatus = ComponentStatus.OFFLINE
    last_seen: Optional[datetime] = None
    last_health_check: Optional[datetime] = None
    
    # Metrics
    recent_metrics: Dict[str, Any] = field(default_factory=dict)
    failed_health_checks: int = 0
    
    def update_health(self, is_healthy: bool, metrics: Optional[Dict] = None):
        """Aktualizuje stan zdrowia komponentu"""
        self.last_health_check = datetime.now()
        
        if is_healthy:
            self.failed_health_checks = 0
            self.status = ComponentStatus.ONLINE
            self.last_seen = datetime.now()
            if metrics:
                self.recent_metrics.update(metrics)
        else:
            self.failed_health_checks += 1
            if self.failed_health_checks >= 3:
                self.status = ComponentStatus.UNRESPONSIVE
    
    def can_transition_to(self, new_state: ComponentState) -> bool:
        """Sprawdza czy komponent może przejść do nowego stanu"""
        from .states import can_transition
        return can_transition(self.state, new_state)
```

**models/events.py:**
```python
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime

class OrchestratorEventType(Enum):
    # Component lifecycle
    COMPONENT_REGISTERED = "component_registered"
    COMPONENT_STATE_CHANGED = "component_state_changed"
    COMPONENT_HEALTH_UPDATED = "component_health_updated"
    
    # Scenario execution
    SCENARIO_STARTED = "scenario_started"
    SCENARIO_COMPLETED = "scenario_completed"
    SCENARIO_FAILED = "scenario_failed"
    
    # System events
    SYSTEM_STARTUP_INITIATED = "system_startup_initiated"
    SYSTEM_SHUTDOWN_INITIATED = "system_shutdown_initiated"
    
    # Error events
    COMPONENT_ERROR_REPORTED = "component_error_reported"
    ORCHESTRATOR_ERROR = "orchestrator_error"

@dataclass
class OrchestratorEvent:
    """Zdarzenie wewnętrzne Orchestratora"""
    event_type: OrchestratorEventType
    component_id: Optional[str] = None
    data: Dict[str, Any] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.data is None:
            self.data = {}
```

### Krok 2: Component Registry (core/component_registry.py)

```python
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
import asyncio
from ..models.component import ComponentInfo
from ..models.states import ComponentState, ComponentStatus
from avena_commons.util.logger import info, warning, error

class ComponentRegistry:
    """Centralny rejestr wszystkich komponentów w systemie"""
    
    def __init__(self):
        self._components: Dict[str, ComponentInfo] = {}
        self._groups: Dict[str, Set[str]] = {}  # group_name -> set of component_ids
        self._dependencies: Dict[str, Set[str]] = {}  # component_id -> dependencies
        self._dependents: Dict[str, Set[str]] = {}   # component_id -> dependents
        self._lock = asyncio.Lock()
    
    async def register_component(self, component_info: ComponentInfo) -> bool:
        """Rejestruje nowy komponent w systemie"""
        async with self._lock:
            if component_info.id in self._components:
                warning(f"Komponent {component_info.id} już jest zarejestrowany")
                return False
            
            self._components[component_info.id] = component_info
            
            # Aktualizacja grup
            for group in component_info.groups:
                if group not in self._groups:
                    self._groups[group] = set()
                self._groups[group].add(component_info.id)
            
            # Aktualizacja zależności
            self._dependencies[component_info.id] = set(component_info.depends_on)
            for dependency in component_info.depends_on:
                if dependency not in self._dependents:
                    self._dependents[dependency] = set()
                self._dependents[dependency].add(component_info.id)
            
            info(f"Zarejestrowano komponent: {component_info.id}")
            return True
    
    async def unregister_component(self, component_id: str) -> bool:
        """Wyrejestrowuje komponent"""
        async with self._lock:
            if component_id not in self._components:
                return False
            
            component = self._components[component_id]
            
            # Usunięcie z grup
            for group in component.groups:
                if group in self._groups:
                    self._groups[group].discard(component_id)
                    if not self._groups[group]:
                        del self._groups[group]
            
            # Usunięcie zależności
            if component_id in self._dependencies:
                del self._dependencies[component_id]
            
            for dep_set in self._dependents.values():
                dep_set.discard(component_id)
            
            if component_id in self._dependents:
                del self._dependents[component_id]
            
            del self._components[component_id]
            info(f"Wyrejestrowano komponent: {component_id}")
            return True
    
    def get_component(self, component_id: str) -> Optional[ComponentInfo]:
        """Pobiera informacje o komponencie"""
        return self._components.get(component_id)
    
    def get_components_in_group(self, group_name: str) -> List[ComponentInfo]:
        """Pobiera wszystkie komponenty w grupie"""
        if group_name not in self._groups:
            return []
        return [self._components[comp_id] for comp_id in self._groups[group_name]]
    
    def get_all_components(self) -> List[ComponentInfo]:
        """Pobiera wszystkie komponenty"""
        return list(self._components.values())
    
    def get_dependencies(self, component_id: str) -> Set[str]:
        """Pobiera zależności komponentu"""
        return self._dependencies.get(component_id, set()).copy()
    
    def get_dependents(self, component_id: str) -> Set[str]:
        """Pobiera komponenty zależne od danego"""
        return self._dependents.get(component_id, set()).copy()
    
    def get_startup_order(self) -> List[List[str]]:
        """Zwraca kolejność uruchamiania komponentów (topological sort)"""
        # Implementacja algorytmu Kahn'a dla sortowania topologicznego
        in_degree = {}
        for comp_id in self._components:
            in_degree[comp_id] = len(self._dependencies.get(comp_id, set()))
        
        queue = [comp_id for comp_id, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            # Wszystkie komponenty z tym samym poziomem zależności
            # mogą być uruchamiane równolegle
            current_level = queue.copy()
            queue.clear()
            result.append(current_level)
            
            for comp_id in current_level:
                for dependent in self._dependents.get(comp_id, set()):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)
        
        return result
    
    def get_shutdown_order(self) -> List[List[str]]:
        """Zwraca kolejność zamykania (odwrócona kolejność startu)"""
        startup_order = self.get_startup_order()
        return list(reversed(startup_order))
    
    async def update_component_state(self, component_id: str, 
                                   new_state: ComponentState) -> bool:
        """Aktualizuje stan komponentu"""
        component = self.get_component(component_id)
        if not component:
            return False
        
        if not component.can_transition_to(new_state):
            warning(f"Nieprawidłowe przejście stanu dla {component_id}: "
                   f"{component.state} -> {new_state}")
            return False
        
        old_state = component.state
        component.state = new_state
        info(f"Zmiana stanu komponentu {component_id}: {old_state} -> {new_state}")
        return True
    
    def get_components_by_state(self, state: ComponentState) -> List[ComponentInfo]:
        """Pobiera komponenty w określonym stanie"""
        return [comp for comp in self._components.values() if comp.state == state]
    
    def get_components_by_status(self, status: ComponentStatus) -> List[ComponentInfo]:
        """Pobiera komponenty o określonym statusie"""
        return [comp for comp in self._components.values() if comp.status == status]
```

### Krok 3: Health Monitor (core/health_monitor.py)

```python
import asyncio
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from ..models.component import ComponentInfo
from ..models.states import ComponentStatus
from avena_commons.event_listener.event import Event
from avena_commons.util.logger import info, warning, error

@dataclass
class HealthCheckConfig:
    """Konfiguracja health check"""
    interval_seconds: int = 30
    timeout_seconds: int = 5
    max_failed_checks: int = 3
    retry_interval_seconds: int = 10

class HealthMonitor:
    """Monitor zdrowia komponentów"""
    
    def __init__(self, orchestrator, config: Optional[HealthCheckConfig] = None):
        self.orchestrator = orchestrator
        self.config = config or HealthCheckConfig()
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}
        self._is_running = False
        self._health_check_callbacks: List[Callable] = []
    
    def add_health_check_callback(self, callback: Callable):
        """Dodaje callback wywoływany przy zmianie stanu zdrowia"""
        self._health_check_callbacks.append(callback)
    
    async def start_monitoring(self):
        """Rozpoczyna monitoring wszystkich komponentów"""
        self._is_running = True
        components = self.orchestrator.component_registry.get_all_components()
        
        for component in components:
            await self.start_monitoring_component(component.id)
        
        info(f"Health monitoring started for {len(components)} components")
    
    async def stop_monitoring(self):
        """Zatrzymuje monitoring"""
        self._is_running = False
        
        # Anulowanie wszystkich zadań monitoringu
        for task in self._monitoring_tasks.values():
            task.cancel()
        
        # Oczekiwanie na zakończenie zadań
        if self._monitoring_tasks:
            await asyncio.gather(*self._monitoring_tasks.values(), 
                                return_exceptions=True)
        
        self._monitoring_tasks.clear()
        info("Health monitoring stopped")
    
    async def start_monitoring_component(self, component_id: str):
        """Rozpoczyna monitoring konkretnego komponentu"""
        if component_id in self._monitoring_tasks:
            return
        
        task = asyncio.create_task(self._monitor_component_loop(component_id))
        self._monitoring_tasks[component_id] = task
        info(f"Started health monitoring for component: {component_id}")
    
    async def stop_monitoring_component(self, component_id: str):
        """Zatrzymuje monitoring komponentu"""
        if component_id in self._monitoring_tasks:
            self._monitoring_tasks[component_id].cancel()
            try:
                await self._monitoring_tasks[component_id]
            except asyncio.CancelledError:
                pass
            del self._monitoring_tasks[component_id]
            info(f"Stopped health monitoring for component: {component_id}")
    
    async def _monitor_component_loop(self, component_id: str):
        """Główna pętla monitoringu komponentu"""
        while self._is_running:
            try:
                await self._perform_health_check(component_id)
                await asyncio.sleep(self.config.interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                error(f"Error in health monitoring for {component_id}: {e}")
                await asyncio.sleep(self.config.retry_interval_seconds)
    
    async def _perform_health_check(self, component_id: str):
        """Wykonuje health check dla komponentu"""
        component = self.orchestrator.component_registry.get_component(component_id)
        if not component:
            return
        
        try:
            # Wysłanie zdarzenia health_check
            health_event = await self.orchestrator._event(
                destination=component_id,
                destination_address=component.address,
                destination_port=component.port,
                event_type="health_check",
                maximum_processing_time=self.config.timeout_seconds
            )
            
            # Sprawdzenie odpowiedzi
            is_healthy = health_event.result and health_event.result.success
            metrics = health_event.result.data if health_event.result else {}
            
            # Aktualizacja stanu zdrowia
            old_status = component.status
            component.update_health(is_healthy, metrics)
            
            # Wywołanie callbacków jeśli status się zmienił
            if old_status != component.status:
                await self._notify_health_status_change(component_id, old_status, component.status)
                
        except asyncio.TimeoutError:
            component.update_health(False)
            warning(f"Health check timeout for component: {component_id}")
            await self._notify_health_status_change(component_id, 
                                                  component.status, 
                                                  ComponentStatus.UNRESPONSIVE)
        except Exception as e:
            component.update_health(False)
            error(f"Health check failed for {component_id}: {e}")
    
    async def _notify_health_status_change(self, component_id: str, 
                                         old_status: ComponentStatus, 
                                         new_status: ComponentStatus):
        """Powiadamia o zmianie statusu zdrowia"""
        info(f"Health status change for {component_id}: {old_status} -> {new_status}")
        
        for callback in self._health_check_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(component_id, old_status, new_status)
                else:
                    callback(component_id, old_status, new_status)
            except Exception as e:
                error(f"Error in health check callback: {e}")
    
    async def force_health_check(self, component_id: str) -> bool:
        """Wymusza natychmiastowy health check"""
        try:
            await self._perform_health_check(component_id)
            component = self.orchestrator.component_registry.get_component(component_id)
            return component.status == ComponentStatus.ONLINE if component else False
        except Exception as e:
            error(f"Forced health check failed for {component_id}: {e}")
            return False
    
    def get_health_summary(self) -> Dict:
        """Zwraca podsumowanie stanu zdrowia wszystkich komponentów"""
        components = self.orchestrator.component_registry.get_all_components()
        summary = {
            "total_components": len(components),
            "online": len([c for c in components if c.status == ComponentStatus.ONLINE]),
            "offline": len([c for c in components if c.status == ComponentStatus.OFFLINE]),
            "unresponsive": len([c for c in components if c.status == ComponentStatus.UNRESPONSIVE]),
            "degraded": len([c for c in components if c.status == ComponentStatus.DEGRADED]),
            "last_updated": datetime.now().isoformat()
        }
        return summary
```

### Krok 4: Główna Klasa Orchestrator (orchestrator.py)

```python
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
import signal
import yaml

from avena_commons.event_listener.event_listener import EventListener
from avena_commons.event_listener.event import Event, Result
from avena_commons.util.logger import info, warning, error, debug

from .core.component_registry import ComponentRegistry
from .core.health_monitor import HealthMonitor, HealthCheckConfig
from .models.component import ComponentInfo
from .models.states import ComponentState, ComponentStatus
from .models.events import OrchestratorEvent, OrchestratorEventType

class Orchestrator(EventListener):
    """Centralny system orkiestracji i monitorowania komponentów"""
    
    def __init__(self, 
                 name: str = "orchestrator",
                 address: str = "127.0.0.1",
                 port: int = 8000,
                 config_file: Optional[str] = None,
                 health_check_config: Optional[HealthCheckConfig] = None,
                 **kwargs):
        
        super().__init__(name=name, address=address, port=port, **kwargs)
        
        # Core components
        self.component_registry = ComponentRegistry()
        self.health_monitor = HealthMonitor(self, health_check_config)
        
        # Configuration
        self.config_file = config_file
        self.system_config: Dict[str, Any] = {}
        
        # State
        self._system_state = "INITIALIZING"
        self._startup_in_progress = False
        self._shutdown_in_progress = False
        
        # Event handlers
        self._orchestrator_event_handlers = {
            "component_register": self._handle_component_register,
            "component_unregister": self._handle_component_unregister,
            "health_check_request": self._handle_health_check_request,
            "get_system_status": self._handle_get_system_status,
            "initiate_system_startup": self._handle_initiate_system_startup,
            "initiate_system_shutdown": self._handle_initiate_system_shutdown,
        }
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    async def _on_initialize(self):
        """Inicjalizacja Orchestratora"""
        info("Initializing Orchestrator...")
        
        # Załadowanie konfiguracji
        if self.config_file:
            await self._load_system_config()
        
        # Setup health monitor callbacks
        self.health_monitor.add_health_check_callback(self._on_component_health_change)
        
        info("Orchestrator initialized successfully")
    
    async def _on_start(self):
        """Start Orchestratora"""
        info("Starting Orchestrator...")
        
        # Start health monitoring
        await self.health_monitor.start_monitoring()
        
        self._system_state = "RUNNING"
        info("Orchestrator started successfully")
    
    async def _on_stop(self):
        """Stop Orchestratora"""
        info("Stopping Orchestrator...")
        
        # Stop health monitoring
        await self.health_monitor.stop_monitoring()
        
        self._system_state = "STOPPED"
        info("Orchestrator stopped")
    
    def _signal_handler(self, signum, frame):
        """Handler dla sygnałów systemowych"""
        info(f"Received signal {signum}, initiating graceful shutdown...")
        asyncio.create_task(self._initiate_graceful_shutdown())
    
    async def _load_system_config(self):
        """Ładuje konfigurację systemu z pliku"""
        try:
            with open(self.config_file, 'r') as f:
                self.system_config = yaml.safe_load(f)
            
            # Pre-register components from config
            if 'components' in self.system_config:
                for comp_config in self.system_config['components']:
                    component_info = ComponentInfo(
                        id=comp_config['id'],
                        name=comp_config.get('name', comp_config['id']),
                        address=comp_config.get('address', '127.0.0.1'),
                        port=comp_config.get('port', 8001),
                        groups=comp_config.get('groups', []),
                        depends_on=comp_config.get('depends_on', []),
                        metadata=comp_config.get('metadata', {})
                    )
                    # Pre-register (komponenty nie są jeszcze online)
                    await self.component_registry.register_component(component_info)
            
            info(f"Loaded system configuration from {self.config_file}")
            
        except Exception as e:
            error(f"Failed to load system configuration: {e}")
            raise
    
    async def _analyze_event(self, event: Event) -> bool:
        """Analizuje przychodzące zdarzenia"""
        # Sprawdź czy to zdarzenie dla Orchestratora
        if event.event_type in self._orchestrator_event_handlers:
            handler = self._orchestrator_event_handlers[event.event_type]
            try:
                await handler(event)
                return True
            except Exception as e:
                error(f"Error handling orchestrator event {event.event_type}: {e}")
                await self._reply(Event(
                    destination=event.source,
                    event_type=event.event_type,
                    id=event.id,
                    result=Result(success=False, message=str(e))
                ))
                return False
        
        # Przekaż do bazowej klasy
        return await super()._analyze_event(event)
    
    # Event Handlers
    async def _handle_component_register(self, event: Event):
        """Obsługuje rejestrację komponentu"""
        try:
            component_data = event.data
            component_info = ComponentInfo(
                id=component_data['id'],
                name=component_data.get('name', component_data['id']),
                address=event.source_address,
                port=event.source_port,
                groups=component_data.get('groups', []),
                depends_on=component_data.get('depends_on', []),
                metadata=component_data.get('metadata', {}),
                state=ComponentState.READY,
                status=ComponentStatus.ONLINE
            )
            
            success = await self.component_registry.register_component(component_info)
            
            if success:
                # Start monitoring tego komponentu
                await self.health_monitor.start_monitoring_component(component_info.id)
                
                await self._reply(Event(
                    destination=event.source,
                    event_type=event.event_type,
                    id=event.id,
                    result=Result(success=True, message="Component registered successfully")
                ))
                
                info(f"Component {component_info.id} registered successfully")
            else:
                await self._reply(Event(
                    destination=event.source,
                    event_type=event.event_type,
                    id=event.id,
                    result=Result(success=False, message="Component already registered")
                ))
        
        except Exception as e:
            error(f"Error registering component: {e}")
            await self._reply(Event(
                destination=event.source,
                event_type=event.event_type,
                id=event.id,
                result=Result(success=False, message=str(e))
            ))
    
    async def _handle_component_unregister(self, event: Event):
        """Obsługuje wyrejestrowanie komponentu"""
        try:
            component_id = event.data.get('component_id', event.source)
            
            # Stop monitoring
            await self.health_monitor.stop_monitoring_component(component_id)
            
            success = await self.component_registry.unregister_component(component_id)
            
            await self._reply(Event(
                destination=event.source,
                event_type=event.event_type,
                id=event.id,
                result=Result(success=success, 
                             message="Component unregistered" if success else "Component not found")
            ))
            
        except Exception as e:
            error(f"Error unregistering component: {e}")
            await self._reply(Event(
                destination=event.source,
                event_type=event.event_type,
                id=event.id,
                result=Result(success=False, message=str(e))
            ))
    
    async def _handle_health_check_request(self, event: Event):
        """Obsługuje żądanie health check"""
        try:
            component_id = event.data.get('component_id')
            
            if component_id:
                # Health check konkretnego komponentu
                is_healthy = await self.health_monitor.force_health_check(component_id)
                component = self.component_registry.get_component(component_id)
                
                result_data = {
                    "component_id": component_id,
                    "is_healthy": is_healthy,
                    "status": component.status.value if component else "NOT_FOUND",
                    "last_seen": component.last_seen.isoformat() if component and component.last_seen else None
                }
            else:
                # Health summary całego systemu
                result_data = self.health_monitor.get_health_summary()
            
            await self._reply(Event(
                destination=event.source,
                event_type=event.event_type,
                id=event.id,
                result=Result(success=True, data=result_data)
            ))
            
        except Exception as e:
            error(f"Error handling health check request: {e}")
            await self._reply(Event(
                destination=event.source,
                event_type=event.event_type,
                id=event.id,
                result=Result(success=False, message=str(e))
            ))
    
    async def _handle_get_system_status(self, event: Event):
        """Obsługuje żądanie statusu systemu"""
        try:
            components = self.component_registry.get_all_components()
            component_status = []
            
            for comp in components:
                component_status.append({
                    "id": comp.id,
                    "name": comp.name,
                    "state": comp.state.value,
                    "status": comp.status.value,
                    "groups": comp.groups,
                    "depends_on": comp.depends_on,
                    "last_seen": comp.last_seen.isoformat() if comp.last_seen else None,
                    "failed_health_checks": comp.failed_health_checks
                })
            
            system_status = {
                "orchestrator_state": self._system_state,
                "total_components": len(components),
                "components": component_status,
                "health_summary": self.health_monitor.get_health_summary(),
                "timestamp": datetime.now().isoformat()
            }
            
            await self._reply(Event(
                destination=event.source,
                event_type=event.event_type,
                id=event.id,
                result=Result(success=True, data=system_status)
            ))
            
        except Exception as e:
            error(f"Error getting system status: {e}")
            await self._reply(Event(
                destination=event.source,
                event_type=event.event_type,
                id=event.id,
                result=Result(success=False, message=str(e))
            ))
    
    async def _handle_initiate_system_startup(self, event: Event):
        """Obsługuje inicjację startu systemu"""
        if self._startup_in_progress:
            await self._reply(Event(
                destination=event.source,
                event_type=event.event_type,
                id=event.id,
                result=Result(success=False, message="System startup already in progress")
            ))
            return
        
        self._startup_in_progress = True
        
        try:
            await self._reply(Event(
                destination=event.source,
                event_type=event.event_type,
                id=event.id,
                result=Result(success=True, message="System startup initiated")
            ))
            
            await self._execute_system_startup()
            
        except Exception as e:
            error(f"Error during system startup: {e}")
        finally:
            self._startup_in_progress = False
    
    async def _handle_initiate_system_shutdown(self, event: Event):
        """Obsługuje inicjację shutdown systemu"""
        if self._shutdown_in_progress:
            await self._reply(Event(
                destination=event.source,
                event_type=event.event_type,
                id=event.id,
                result=Result(success=False, message="System shutdown already in progress")
            ))
            return
        
        await self._reply(Event(
            destination=event.source,
            event_type=event.event_type,
            id=event.id,
            result=Result(success=True, message="System shutdown initiated")
        ))
        
        await self._initiate_graceful_shutdown()
    
    # System Operations
    async def _execute_system_startup(self):
        """Wykonuje sekwencję startu systemu"""
        info("Executing system startup sequence...")
        
        startup_order = self.component_registry.get_startup_order()
        
        for level, component_ids in enumerate(startup_order):
            info(f"Starting level {level + 1}: {component_ids}")
            
            # Równoległe wysłanie komend do wszystkich komponentów na tym poziomie
            tasks = []
            for component_id in component_ids:
                component = self.component_registry.get_component(component_id)
                if component and component.status == ComponentStatus.ONLINE:
                    task = self._send_component_command(component_id, "CMD_INITIALIZE")
                    tasks.append(task)
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
                # Oczekiwanie na przejście do stanu INIT_COMPLETE
                await self._wait_for_components_state(component_ids, ComponentState.INIT_COMPLETE, timeout=60)
        
        # Finalne uruchomienie wszystkich komponentów
        info("Sending CMD_START to all components...")
        all_components = [comp.id for comp in self.component_registry.get_all_components()]
        start_tasks = [self._send_component_command(comp_id, "CMD_START") 
                      for comp_id in all_components]
        
        await asyncio.gather(*start_tasks, return_exceptions=True)
        await self._wait_for_components_state(all_components, ComponentState.STARTED, timeout=30)
        
        info("System startup sequence completed")
    
    async def _initiate_graceful_shutdown(self):
        """Inicjuje graceful shutdown systemu"""
        if self._shutdown_in_progress:
            return
        
        self._shutdown_in_progress = True
        info("Initiating graceful system shutdown...")
        
        try:
            shutdown_order = self.component_registry.get_shutdown_order()
            
            for level, component_ids in enumerate(shutdown_order):
                info(f"Stopping level {level + 1}: {component_ids}")
                
                # Równoległe wysłanie komend STOP
                stop_tasks = [self._send_component_command(comp_id, "CMD_GRACEFUL_STOP") 
                             for comp_id in component_ids]
                
                await asyncio.gather(*stop_tasks, return_exceptions=True)
                
                # Oczekiwanie na przejście do stanu STOPPED
                await self._wait_for_components_state(component_ids, ComponentState.STOPPED, timeout=60)
            
            info("Graceful system shutdown completed")
            
        except Exception as e:
            error(f"Error during graceful shutdown: {e}")
        finally:
            self._shutdown_in_progress = False
            # Shutdown self
            await self.shutdown()
    
    async def _send_component_command(self, component_id: str, command: str):
        """Wysyła komendę do komponentu"""
        component = self.component_registry.get_component(component_id)
        if not component:
            warning(f"Component {component_id} not found")
            return
        
        try:
            await self._event(
                destination=component_id,
                destination_address=component.address,
                destination_port=component.port,
                event_type=command,
                maximum_processing_time=30
            )
            debug(f"Sent {command} to {component_id}")
            
        except Exception as e:
            error(f"Error sending {command} to {component_id}: {e}")
    
    async def _wait_for_components_state(self, component_ids: List[str], 
                                       target_state: ComponentState, 
                                       timeout: int = 30):
        """Oczekuje aż komponenty przejdą do określonego stanu"""
        start_time = datetime.now()
        
        while (datetime.now() - start_time).total_seconds() < timeout:
            all_ready = True
            
            for component_id in component_ids:
                component = self.component_registry.get_component(component_id)
                if not component or component.state != target_state:
                    all_ready = False
                    break
            
            if all_ready:
                info(f"All components reached state {target_state.name}")
                return
            
            await asyncio.sleep(1)
        
        # Timeout - log which components didn't make it
        not_ready = []
        for component_id in component_ids:
            component = self.component_registry.get_component(component_id)
            if not component or component.state != target_state:
                not_ready.append(f"{component_id}({component.state.name if component else 'NOT_FOUND'})")
        
        warning(f"Timeout waiting for components to reach {target_state.name}. "
               f"Not ready: {not_ready}")
    
    async def _on_component_health_change(self, component_id: str, 
                                        old_status: ComponentStatus, 
                                        new_status: ComponentStatus):
        """Callback wywoływany przy zmianie statusu zdrowia komponentu"""
        info(f"Component {component_id} health changed: {old_status} -> {new_status}")
        
        # Tu można dodać logikę automatycznej reakcji na zmiany statusu
        if new_status == ComponentStatus.UNRESPONSIVE:
            warning(f"Component {component_id} became unresponsive - consider recovery actions")
            # TODO: Trigger recovery scenario
        elif new_status == ComponentStatus.ONLINE and old_status == ComponentStatus.UNRESPONSIVE:
            info(f"Component {component_id} recovered from unresponsive state")
    
    # Public API Methods
    async def register_component_external(self, component_info: ComponentInfo) -> bool:
        """Publiczne API do rejestracji komponentu"""
        return await self.component_registry.register_component(component_info)
    
    def get_system_health_summary(self) -> Dict:
        """Publiczne API do pobrania podsumowania zdrowia systemu"""
        return self.health_monitor.get_health_summary()
    
    def get_component_info(self, component_id: str) -> Optional[ComponentInfo]:
        """Publiczne API do pobrania informacji o komponencie"""
        return self.component_registry.get_component(component_id)
    
    def get_all_components_info(self) -> List[ComponentInfo]:
        """Publiczne API do pobrania informacji o wszystkich komponentach"""
        return self.component_registry.get_all_components()
```

## Testy dla Poziomu 0

### tests/unit/orchestrator/test_orchestrator_basic.py

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from avena_commons.orchestrator.orchestrator import Orchestrator
from avena_commons.orchestrator.models.component import ComponentInfo
from avena_commons.orchestrator.models.states import ComponentState, ComponentStatus

class TestOrchestratorBasic:
    
    @pytest.fixture
    async def orchestrator(self):
        """Fixture dla podstawowego Orchestratora"""
        orch = Orchestrator(name="test_orchestrator", port=8999)
        await orch._on_initialize()
        yield orch
        await orch.shutdown()
    
    @pytest.fixture
    def sample_component_info(self):
        """Fixture dla przykładowych danych komponentu"""
        return ComponentInfo(
            id="test_component",
            name="Test Component",
            address="127.0.0.1",
            port=8001,
            groups=["test_group"],
            depends_on=[],
            metadata={"version": "1.0.0"}
        )
    
    async def test_orchestrator_initialization(self, orchestrator):
        """Test inicjalizacji Orchestratora"""
        assert orchestrator is not None
        assert orchestrator.component_registry is not None
        assert orchestrator.health_monitor is not None
        assert orchestrator._system_state == "INITIALIZING"
    
    async def test_component_registration(self, orchestrator, sample_component_info):
        """Test rejestracji komponentu"""
        # Test successful registration
        success = await orchestrator.register_component_external(sample_component_info)
        assert success is True
        
        # Verify component is registered
        registered_component = orchestrator.get_component_info("test_component")
        assert registered_component is not None
        assert registered_component.id == "test_component"
        assert registered_component.name == "Test Component"
        assert registered_component.groups == ["test_group"]
        
        # Test duplicate registration
        success = await orchestrator.register_component_external(sample_component_info)
        assert success is False
    
    async def test_component_unregistration(self, orchestrator, sample_component_info):
        """Test wyrejestrowania komponentu"""
        # Register first
        await orchestrator.register_component_external(sample_component_info)
        
        # Unregister
        success = await orchestrator.component_registry.unregister_component("test_component")
        assert success is True
        
        # Verify component is unregistered
        component = orchestrator.get_component_info("test_component")
        assert component is None
        
        # Test unregistering non-existent component
        success = await orchestrator.component_registry.unregister_component("non_existent")
        assert success is False
    
    async def test_system_health_summary(self, orchestrator, sample_component_info):
        """Test podsumowania zdrowia systemu"""
        # Initially no components
        summary = orchestrator.get_system_health_summary()
        assert summary["total_components"] == 0
        assert summary["online"] == 0
        
        # Add component
        await orchestrator.register_component_external(sample_component_info)
        
        # Update summary - component should be offline initially (no real communication)
        summary = orchestrator.get_system_health_summary()
        assert summary["total_components"] == 1
    
    async def test_get_all_components(self, orchestrator):
        """Test pobierania wszystkich komponentów"""
        # Initially empty
        components = orchestrator.get_all_components_info()
        assert len(components) == 0
        
        # Add multiple components
        component1 = ComponentInfo(id="comp1", name="Component 1", address="127.0.0.1", port=8001)
        component2 = ComponentInfo(id="comp2", name="Component 2", address="127.0.0.1", port=8002)
        
        await orchestrator.register_component_external(component1)
        await orchestrator.register_component_external(component2)
        
        components = orchestrator.get_all_components_info()
        assert len(components) == 2
        assert any(comp.id == "comp1" for comp in components)
        assert any(comp.id == "comp2" for comp in components)
    
    async def test_orchestrator_start_stop(self, orchestrator):
        """Test startu i stopu Orchestratora"""
        # Start
        await orchestrator._on_start()
        assert orchestrator._system_state == "RUNNING"
        
        # Stop
        await orchestrator._on_stop()
        assert orchestrator._system_state == "STOPPED"

class TestOrchestratorErrorHandling:
    
    @pytest.fixture
    async def orchestrator(self):
        """Fixture dla Orchestratora"""
        orch = Orchestrator(name="test_orchestrator", port=8999)
        await orch._on_initialize()
        yield orch
        await orch.shutdown()
    
    async def test_register_invalid_component(self, orchestrator):
        """Test rejestracji nieprawidłowego komponentu"""
        # Component with empty ID should be rejected
        invalid_component = ComponentInfo(
            id="",  # Empty ID
            name="Invalid Component",
            address="127.0.0.1",
            port=8001
        )
        
        with pytest.raises(Exception):
            await orchestrator.register_component_external(invalid_component)
    
    async def test_get_nonexistent_component(self, orchestrator):
        """Test pobierania nieistniejącego komponentu"""
        component = orchestrator.get_component_info("nonexistent")
        assert component is None
```

### tests/unit/orchestrator/test_component_registry.py

```python
import pytest
from avena_commons.orchestrator.core.component_registry import ComponentRegistry
from avena_commons.orchestrator.models.component import ComponentInfo
from avena_commons.orchestrator.models.states import ComponentState, ComponentStatus

class TestComponentRegistry:
    
    @pytest.fixture
    def registry(self):
        """Fixture dla ComponentRegistry"""
        return ComponentRegistry()
    
    @pytest.fixture
    def sample_components(self):
        """Fixture dla przykładowych komponentów"""
        return [
            ComponentInfo(id="io", name="IO Service", address="127.0.0.1", port=8001, groups=["base_io"]),
            ComponentInfo(id="algo", name="Algorithm", address="127.0.0.1", port=8002, 
                         groups=["main_logic"], depends_on=["io"]),
            ComponentInfo(id="supervisor1", name="Supervisor 1", address="127.0.0.1", port=8003,
                         groups=["supervisors"], depends_on=["io", "algo"]),
            ComponentInfo(id="supervisor2", name="Supervisor 2", address="127.0.0.1", port=8004,
                         groups=["supervisors"], depends_on=["io", "algo"]),
            ComponentInfo(id="kds", name="KDS", address="127.0.0.1", port=8005,
                         groups=["core_services"], depends_on=["algo"])
        ]
    
    async def test_register_component(self, registry, sample_components):
        """Test rejestracji komponentu"""
        component = sample_components[0]  # io
        
        success = await registry.register_component(component)
        assert success is True
        
        # Verify registration
        registered = registry.get_component("io")
        assert registered is not None
        assert registered.id == "io"
        assert registered.name == "IO Service"
        
        # Test duplicate registration
        success = await registry.register_component(component)
        assert success is False
    
    async def test_unregister_component(self, registry, sample_components):
        """Test wyrejestrowania komponentu"""
        component = sample_components[0]
        
        # Register first
        await registry.register_component(component)
        
        # Unregister
        success = await registry.unregister_component("io")
        assert success is True
        
        # Verify unregistration
        component = registry.get_component("io")
        assert component is None
        
        # Test unregistering non-existent
        success = await registry.unregister_component("nonexistent")
        assert success is False
    
    async def test_group_management(self, registry, sample_components):
        """Test zarządzania grupami"""
        # Register components
        for comp in sample_components[:3]:  # io, algo, supervisor1
            await registry.register_component(comp)
        
        # Test getting components in group
        base_io_components = registry.get_components_in_group("base_io")
        assert len(base_io_components) == 1
        assert base_io_components[0].id == "io"
        
        main_logic_components = registry.get_components_in_group("main_logic")
        assert len(main_logic_components) == 1
        assert main_logic_components[0].id == "algo"
        
        supervisors = registry.get_components_in_group("supervisors")
        assert len(supervisors) == 1
        assert supervisors[0].id == "supervisor1"
        
        # Test non-existent group
        empty_group = registry.get_components_in_group("nonexistent")
        assert len(empty_group) == 0
    
    async def test_dependency_management(self, registry, sample_components):
        """Test zarządzania zależnościami"""
        # Register components
        for comp in sample_components:
            await registry.register_component(comp)
        
        # Test getting dependencies
        io_deps = registry.get_dependencies("io")
        assert len(io_deps) == 0  # io has no dependencies
        
        algo_deps = registry.get_dependencies("algo")
        assert len(algo_deps) == 1
        assert "io" in algo_deps
        
        supervisor1_deps = registry.get_dependencies("supervisor1")
        assert len(supervisor1_deps) == 2
        assert "io" in supervisor1_deps
        assert "algo" in supervisor1_deps
        
        # Test getting dependents
        io_dependents = registry.get_dependents("io")
        assert len(io_dependents) == 3  # algo, supervisor1, supervisor2
        assert "algo" in io_dependents
        assert "supervisor1" in io_dependents
        assert "supervisor2" in io_dependents
        
        algo_dependents = registry.get_dependents("algo")
        assert len(algo_dependents) == 3  # supervisor1, supervisor2, kds
        assert "supervisor1" in algo_dependents
        assert "supervisor2" in algo_dependents
        assert "kds" in algo_dependents
    
    async def test_startup_order(self, registry, sample_components):
        """Test kolejności uruchamiania"""
        # Register components
        for comp in sample_components:
            await registry.register_component(comp)
        
        startup_order = registry.get_startup_order()
        
        # Should have 3 levels:
        # Level 0: io (no dependencies)
        # Level 1: algo (depends on io)  
        # Level 2: supervisor1, supervisor2, kds (depend on algo and/or io)
        assert len(startup_order) == 3
        
        assert "io" in startup_order[0]
        assert "algo" in startup_order[1]
        assert all(comp in startup_order[2] for comp in ["supervisor1", "supervisor2", "kds"])
    
    async def test_shutdown_order(self, registry, sample_components):
        """Test kolejności zamykania"""
        # Register components
        for comp in sample_components:
            await registry.register_component(comp)
        
        shutdown_order = registry.get_shutdown_order()
        startup_order = registry.get_startup_order()
        
        # Shutdown order should be reverse of startup order
        assert len(shutdown_order) == len(startup_order)
        assert shutdown_order == list(reversed(startup_order))
    
    async def test_state_management(self, registry, sample_components):
        """Test zarządzania stanami"""
        component = sample_components[0]
        await registry.register_component(component)
        
        # Test valid state transition
        success = await registry.update_component_state("io", ComponentState.INITIALIZING)
        assert success is True
        
        updated_component = registry.get_component("io")
        assert updated_component.state == ComponentState.INITIALIZING
        
        # Test invalid state transition (UNKNOWN -> STARTED without going through proper sequence)
        component.state = ComponentState.UNKNOWN
        success = await registry.update_component_state("io", ComponentState.STARTED)
        assert success is False  # Should reject invalid transition
    
    async def test_components_by_state(self, registry, sample_components):
        """Test filtrowania komponentów po stanie"""
        # Register and set different states
        await registry.register_component(sample_components[0])  # io
        await registry.register_component(sample_components[1])  # algo
        
        await registry.update_component_state("io", ComponentState.STARTED)
        await registry.update_component_state("algo", ComponentState.INITIALIZING)
        
        # Test filtering
        started_components = registry.get_components_by_state(ComponentState.STARTED)
        assert len(started_components) == 1
        assert started_components[0].id == "io"
        
        initializing_components = registry.get_components_by_state(ComponentState.INITIALIZING)
        assert len(initializing_components) == 1
        assert initializing_components[0].id == "algo"
        
        ready_components = registry.get_components_by_state(ComponentState.READY)
        assert len(ready_components) == 0
    
    async def test_components_by_status(self, registry, sample_components):
        """Test filtrowania komponentów po statusie"""
        component1 = sample_components[0]
        component2 = sample_components[1]
        
        await registry.register_component(component1)
        await registry.register_component(component2)
        
        # Set different statuses
        component1.status = ComponentStatus.ONLINE
        component2.status = ComponentStatus.UNRESPONSIVE
        
        online_components = registry.get_components_by_status(ComponentStatus.ONLINE)
        assert len(online_components) == 1
        assert online_components[0].id == "io"
        
        unresponsive_components = registry.get_components_by_status(ComponentStatus.UNRESPONSIVE)
        assert len(unresponsive_components) == 1
        assert unresponsive_components[0].id == "algo"
```

## Kryteria Akceptacji dla Poziomu 0

### Funkcjonalne:
- [ ] **Component Registration**: Orchestrator może rejestrować komponenty z pełnymi informacjami
- [ ] **Health Monitoring**: Podstawowy health check z timeout detection
- [ ] **State Tracking**: Śledzenie stanów FSM wszystkich komponentów
- [ ] **Group Management**: Organizacja komponentów w grupy funkcjonalne
- [ ] **Dependency Awareness**: Znajomość zależności między komponentami
- [ ] **Basic Commands**: Wysyłanie podstawowych komend (START, STOP, INITIALIZE)

### Techniczne:
- [ ] **Test Coverage**: Minimum 95% line coverage
- [ ] **Performance**: Obsługa 10 komponentów z <100ms response time
- [ ] **Memory**: Stabilne zużycie pamięci (no leaks w 1-godzinnym teście)
- [ ] **Error Handling**: Graceful handling błędów komunikacji
- [ ] **Logging**: Structured logging wszystkich operacji
- [ ] **Documentation**: Complete API documentation

### Integration:
- [ ] **EventListener Integration**: Bezproblemowa komunikacja z istniejącymi komponentami
- [ ] **Configuration Loading**: Ładowanie konfiguracji z YAML
- [ ] **Signal Handling**: Graceful shutdown na SIGINT/SIGTERM
- [ ] **Mock Testing**: Kompletne testy z mock komponentami

Ten plan zapewnia solidną podstawę dla systemu Orchestrator z możliwością iteracyjnego rozbudowywania o zaawansowane funkcjonalności w kolejnych poziomach.
