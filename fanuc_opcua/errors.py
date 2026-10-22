class FanucError(Exception):
    """Base class for all errors raised by fanuc_opcua."""


class AddressError(FanucError, ValueError):
    """An address string such as "DO[1]" could not be parsed or is out of range."""


class ReadOnlyError(FanucError):
    """The address cannot be written over OPC UA (e.g. DI, GI, current position)."""


class CommunicationError(FanucError):
    """The server answered a read or write with a bad status code."""

    def __init__(self, message: str, status: str = ""):
        super().__init__(f"{message}: {status}" if status else message)
        self.status = status


class FanucConnectionError(FanucError, ConnectionError):
    """The OPC UA server could not be reached."""


class NotConnectedError(FanucError):
    """An operation was attempted before connect() or after disconnect()."""
