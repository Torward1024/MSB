"""The exceptions MSB raises.

What a caller may catch is part of the contract, so the framework raises its own types rather
than bare built-ins. Every one of them derives from `MSBError`, and also from the built-in it
replaces, so existing `except TypeError` and `except ValueError` handlers keep working
unchanged. Nothing about the messages or the moments they are raised has changed.

    MSBError
    |-- ValidationError                 the data given to MSB is wrong
    |   |-- TypeValidationError             a value does not match its annotation
    |   |-- ConstraintError                 a value fails a value constraint
    |   |-- UnknownAttributeError           an attribute that was never declared
    |   `-- ItemNameError                   an item's name is unusable in a container
    |       `-- DuplicateNameError              ...because something already has it
    |-- ResolutionError                 a type could not be resolved
    |-- NotFoundError                   a name was looked up and is not there
    |   `-- AttributeNotFoundError          ...and the name was an attribute
    |-- SerializationError              a round trip through a dictionary failed
    `-- OperationError                  the operation layer
        |-- RegistrationError               an operation was registered wrongly
        |-- DispatchError                   nothing can serve this object
        |-- RequestError                    the request itself is malformed
        `-- HandlerError                    a handler ran and failed

Three levels, so a caller can be as broad or as narrow as it wants: `except MSBError` for
anything from the framework, `except ValidationError` for bad input, `except TypeError` for
the same code that worked before.

Two of these derive from more than one built-in, because the sites they replace did not agree
on one. A malformed request was a `TypeError` when the request was not a dictionary and a
`ValueError` when it was the wrong dictionary; a failed round trip was either, depending on
which layer noticed. Both keep every existing handler working, at the price of a class that
answers to two names.
"""

__all__ = [
    "MSBError",
    "ValidationError",
    "TypeValidationError",
    "ConstraintError",
    "UnknownAttributeError",
    "ItemNameError",
    "DuplicateNameError",
    "ResolutionError",
    "NotFoundError",
    "AttributeNotFoundError",
    "SerializationError",
    "OperationError",
    "RegistrationError",
    "DispatchError",
    "RequestError",
    "HandlerError",
]


class MSBError(Exception):
    """Anything the framework raises.

    Catch this to mean "MSB rejected something", without caring what.
    """


class ValidationError(MSBError):
    """The data handed to MSB does not satisfy what the model declares.

    Never raised directly: one of the four subclasses below says what was wrong with it.
    """


class TypeValidationError(ValidationError, TypeError):
    """A value does not match the type its annotation declares.

    Raised while validating an attribute against `_fields`, and while checking that an item
    added to a container is of the container's item type.
    """


class ConstraintError(ValidationError, ValueError):
    """A value is of the right type and still not allowed.

    What the helpers in `utils.validation` raise: not positive, out of range, empty.
    """


class UnknownAttributeError(ValidationError, ValueError):
    """An attribute was supplied that the class never declared.

    A typo in a keyword argument or in a `set` mapping reaches the caller here rather than
    being silently stored.
    """


class ItemNameError(ValidationError, ValueError):
    """An item cannot go into a container under that name.

    A container keys its items by `name`, so an item with no name, or one whose name
    disagrees with the key it is filed under, has nowhere to go.
    """


class DuplicateNameError(ItemNameError):
    """The container already holds an item under that name.

    Adding never overwrites: replacing an item is `set_item`, and the difference is worth an
    exception rather than a lost object.
    """


class ResolutionError(MSBError, TypeError):
    """A type could not be resolved to a class.

    Raised for an unresolvable forward reference, an unparameterized generic container, a
    `TypeVar` with nothing to bind it to, and a type name in serialized data that matches no
    registered class or matches several of them ambiguously.
    """


class NotFoundError(MSBError, KeyError):
    """A name was looked up and is not there.

    An attribute of an entity, or an item of a container: both are addressed by name, and
    both report a miss the same way.
    """


class AttributeNotFoundError(NotFoundError, AttributeError):
    """A query named an attribute the items do not have.

    Separate from `NotFoundError` only so that `except AttributeError` still catches it,
    which is how a filter over items reported this before.
    """


class SerializationError(MSBError, ValueError, TypeError):
    """A round trip through a dictionary failed.

    Restoring an object whose payload is malformed, whose declared type does not fit the
    field, or which carries a cyclic-reference marker that cannot be turned back into an
    object.
    """


class OperationError(MSBError):
    """Something went wrong in the operation layer rather than in the data.

    Never raised directly; the four subclasses below say which part.
    """


class RegistrationError(OperationError, ValueError):
    """An operation cannot be registered as asked.

    A missing or unusable operation name, a super-instance without `execute`, or a name that
    another user registration already claims. A user registration replacing a built-in is
    not this: that is allowed and silent.
    """


class DispatchError(OperationError, ValueError):
    """Nothing is registered that can serve this object.

    No operation for its type, no methods for its type, or no handler matching the operation
    and the object together.
    """


class RequestError(OperationError, ValueError, TypeError):
    """The request is malformed.

    Not a dictionary, a batch that is neither a sequence nor a mapping, an entry in one that
    is not a request, or a request naming no methods at all.
    """


class HandlerError(OperationError, RuntimeError):
    """A handler ran and failed.

    Raised where a failure is meant to propagate rather than be reported: a facade called
    with `raise_on_error=True`, a batch with `raise_on_error=True`, and `_apply_methods` in
    strict mode. Where the framework still holds the original exception -- which it does in
    strict mode, and does not once the failure has been reduced to a message in a response --
    it is attached as the cause, so the traceback that matters stays reachable through
    `__cause__`.
    """
