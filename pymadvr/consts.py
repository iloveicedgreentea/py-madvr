"""Constants for madvr module."""

REFRESH_TIME = 20
PING_DELAY = 30
COMMAND_TIMEOUT = 3
PING_INTERVAL = 10  # Check device availability every 10 seconds
HEARTBEAT_INTERVAL = 15
CONNECT_TIMEOUT = 5
DEFAULT_PORT = 44077
READ_LIMIT = 8000
SMALL_DELAY = 2
# save some cpu cycles
TASK_CPU_DELAY = 1.0
MAX_COMMAND_QUEUE_SIZE = 100  # Maximum number of commands to buffer

# Connection pool timeouts - all network operations should complete quickly on local network
COMMAND_RESPONSE_TIMEOUT = 0.5
HEARTBEAT_TIMEOUT = 0.5
CONNECTION_TIMEOUT = 1  # 1 second for establishing TCP connection
COMMAND_RETRY_ATTEMPTS = 2  # Number of attempts to send a command (1 initial + 1 retry)
CONNECTION_POOL_MAX_SIZE = 5  # Maximum number of connections to keep in pool
