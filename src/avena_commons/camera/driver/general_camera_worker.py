from typing import Optional
from avena_commons.util.logger import MessageLogger
from avena_commons.camera.driver.general import CameraState
from avena_commons.util.logger import MessageLogger, debug


class GeneralCameraWorker():
    def __init__(self, message_logger: Optional[MessageLogger] = None):
        # Zarządzanie kamerą (już masz)
        self._message_logger = None
        self.device_name = f"GeneralCamera"
        super().__init__(message_logger=None)
        self.state = CameraState.IDLE
        self.last_frames = None
        
        # Przetwarzanie obrazów (dodaj to)
        self.postprocess_configuration = None
        self.image_processing_methods = {}  # Zmień nazwę!
        
    async def _setup_image_processing(self, configs: list):
        """Przygotuj metody przetwarzania obrazów."""
        self.image_processing_methods = {}
        
        for i, config in enumerate(configs):
            # Każda konfiguracja ma swoją metodę przetwarzania
            method_name = f"process_config_{i}"
            self.image_processing_methods[i] = {
                "config": config,
                "method": method_name
            }
        
        debug(f"Przygotowano {len(self.image_processing_methods)} metod przetwarzania", 
              self._message_logger)
    
    async def _process_frame_with_all_configs(self, frames):
        """Przetwórz klatkę wszystkimi konfiguracjami."""
        if not self.image_processing_methods:
            return []
        
        results = []
        
        # Przetwórz każdą konfiguracją
        for config_id, method_info in self.image_processing_methods.items():
            try:
                config = method_info["config"]
                method_name = method_info["method"]
                
                # Wywołaj odpowiednią metodę
                result = await getattr(self, method_name)(frames, config)
                results.append({
                    "config_id": config_id,
                    "config": config,
                    "result": result,
                    "success": True
                })
                
            except Exception as e:
                results.append({
                    "config_id": config_id,
                    "config": config,
                    "error": str(e),
                    "success": False
                })
        
        return results