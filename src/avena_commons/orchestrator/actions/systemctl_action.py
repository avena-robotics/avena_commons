import asyncio
from typing import Any, Dict, List, Tuple

from avena_commons.util.logger import debug, info, warning

from .base_action import ActionContext, ActionExecutionError, BaseAction


class SystemctlAction(BaseAction):
    """
    Akcja wykonująca operacje systemd (systemctl) na wskazanych usługach.

    Konfiguracja:
    - type: "systemctl"
    - operation: "stop" | "start" | "restart" | "reload" | "enable" | "disable" | "status" (domyślnie: "stop")
    - service: "nazwa.service"            # pojedyncza usługa (opcjonalnie)
    - services: ["a.service", "b.service"]# wiele usług (opcjonalnie)
    - use_sudo: bool                      # domyślnie False (jeśli potrzebujesz sudo -n)
    - timeout: "30s" | "2m" | liczba      # domyślnie 30s
    - ignore_errors: bool                 # domyślnie False

    Przykład:
    {
      "type": "systemctl",
      "operation": "stop",
      "services": ["nginx.service", "redis-server.service"],
      "timeout": "20s",
      "use_sudo": false
    }
    """

    _ALLOWED_OPS = {"stop", "start", "restart", "reload", "enable", "disable", "status"}

    async def execute(
        self, action_config: Dict[str, Any], context: ActionContext
    ) -> None:
        operation = str(action_config.get("operation", "stop")).lower()
        if operation not in self._ALLOWED_OPS:
            raise ActionExecutionError(
                "systemctl", f"Nieobsługiwana operacja: {operation}"
            )

        # Zbierz listę usług
        services = self._collect_services(action_config)
        if not services:
            raise ActionExecutionError(
                "systemctl", "Nie podano usług (service/services)"
            )

        use_sudo = bool(action_config.get("use_sudo", False))
        timeout_str = action_config.get("timeout", "30s")
        timeout_sec = self._parse_timeout(timeout_str)
        ignore_errors = bool(action_config.get("ignore_errors", False))

        info(
            f"systemctl: {operation} dla {len(services)} usług: {services}",
            message_logger=context.message_logger,
        )

        for svc in services:
            cmd = (
                ["sudo", "-n", "systemctl", operation, svc]
                if use_sudo
                else ["systemctl", operation, svc]
            )

            rc, out, err = await self._run(cmd, timeout_sec)
            debug(
                f"systemctl cmd: {cmd} -> rc={rc}, out='{out.strip()}', err='{err.strip()}'",
                message_logger=context.message_logger,
            )

            if rc != 0:
                msg = f"systemctl {operation} {svc} nie powiodło się (rc={rc}): {err.strip() or out.strip()}"
                if ignore_errors:
                    warning(msg, message_logger=context.message_logger)
                    continue
                raise ActionExecutionError("systemctl", msg)

            info(
                f"systemctl: {operation} OK dla {svc}",
                message_logger=context.message_logger,
            )

    def _collect_services(self, cfg: Dict[str, Any]) -> List[str]:
        services: List[str] = []
        if "service" in cfg and cfg["service"]:
            services.append(str(cfg["service"]))
        if "services" in cfg and isinstance(cfg["services"], list):
            services.extend(str(s) for s in cfg["services"] if s)
        # usunięcie duplikatów, zachowanie kolejności
        seen = set()
        uniq = []
        for s in services:
            if s not in seen:
                uniq.append(s)
                seen.add(s)
        return uniq

    async def _run(self, cmd: List[str], timeout_sec: float) -> Tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_sec
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise ActionExecutionError(
                "systemctl", f"Przekroczono timeout {timeout_sec}s dla: {' '.join(cmd)}"
            )

        return (
            proc.returncode,
            stdout_b.decode(errors="ignore"),
            stderr_b.decode(errors="ignore"),
        )
