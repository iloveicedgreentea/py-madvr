"""Errors for madvr"""

class AckError(Exception):
    """An error when ACK is not correct"""


class RetryExceededError(Exception):
    """Too many retries"""


class HeartBeatError(Exception):
    """An error has occured with heartbeats"""
