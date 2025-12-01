from enum import Enum


class MdbTransactionResult(Enum):
    """Transaction result states"""

    NONE = "none"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"

class MdbStatus(Enum):
    """Status states for MDB service"""

    DISCONNECTED = "disconnected"
    OPENING_PORT = "opening_port"
    CONNECTING = "connecting"
    RESTARTING_CASHLESS = "restarting_cashless"
    INITIALIZING = "initializing"
    STARTING = "starting"
    IDLE = "idle"
    PROCESSING_SEND_COMMAND = "processing_send_command"
    PROCESSING_WAIT_STATUS_VEND = "processing_wait_status_vend"
    PROCESSING_WAIT_STATUS_RESULT = "processing_wait_status_result"
    SENDING_END_AFTER_RESULT = "sending_end_after_result"
    SENDING_END_AFTER_FAILED_RESULT = "sending_end_after_failed_result"
    WAITING_AFTER_PAYMENT = "waiting_after_payment"
