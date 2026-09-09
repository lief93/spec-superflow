class LayoutExpressionError(ValueError):
    pass


class KnownValueError(LayoutExpressionError):
    """A supported operation failed on a known value, not an unknown expression."""
