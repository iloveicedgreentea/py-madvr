class AckError(Exception):
    """An error when ACK is not correct"""

class RetryExceededError(Exception):
    """Too many retries"""