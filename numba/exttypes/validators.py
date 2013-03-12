# -*- coding: utf-8 -*-

"""
Validate method signatures and inheritance compatiblity.
"""

import warnings
import inspect

import numba
from numba import *
from numba import error

from numba.typesystem.exttypes import ordering


#------------------------------------------------------------------------
# Method Validators
#------------------------------------------------------------------------

class MethodValidator(object):
    "Interface for method validators"

    def validate(self, method, ext_type):
        """
        Validate a Method. Raise an exception for user typing errors.
        """

class ArgcountMethodValidator(MethodValidator):
    """
    Validate a signature against the number of arguments the function expects.
    """

    def validate(self, method, ext_type):
        """
        Validate a signature (which is None if not declared by the user)
        for a method.
        """
        if method.signature is None:
            return

        nargs = method.py_func.__code__.co_argcount - 1 + method.is_static
        if len(method.signature.args) != nargs:
            raise error.NumbaError(
                "Expected %d argument types in function "
                "%s (don't include 'self')" % (nargs, method.name))

class InitMethodValidator(MethodValidator):
    """
    Validate the init method of extension classes.
    """

    def validate(self, method, ext_type):
        if method.name == '__init__' and (method.is_class or method.is_static):
            raise error.NumbaError("__init__ method should not be a class- "
                                   "or staticmethod")

class JitInitMethodValidator(MethodValidator):
    """
    Validate the init method for jit functions. Issue a warning when the
    signature is omitted.
    """

    def validate(self, method, ext_type):
        if method.name == '__init__' and method.signature is None:
            self.check_init_args(method, ext_type)

    def check_init_args(self, method, ext_type):
        if inspect.getargspec(method.py_func).args:
            warnings.warn(
                "Constructor for class '%s' has no signature, "
                "assuming arguments have type 'object'" %
                ext_type.py_class.__name__)


jit_validators = [ArgcountMethodValidator(), InitMethodValidator(), JitInitMethodValidator()]
autojit_validators = [ArgcountMethodValidator(), InitMethodValidator()]

#------------------------------------------------------------------------
# Inheritance and Table Validators
#------------------------------------------------------------------------

class ExtTypeValidator(object):
    """
    Interface for validators that check for compatible inheritance trees.
    """

    def validate(self, ext_type):
        """
        Validate an extension type with its parents.
        """

# ______________________________________________________________________
# Validate Table Ordering

class AttributeTableOrderValidator(ExtTypeValidator):
    "Validate attribute table with static order (non-hash-based)."

    def validate(self, ext_type):
        ordering.validate_extending_order_compatibility(
            ordering.AttributeTable(ext_type.attribute_table))

class MethodTableOrderValidator(ExtTypeValidator):
    "Validate method table with static order (non-hash-based)."

    def validate(self, ext_type):
        ordering.validate_extending_order_compatibility(
            ordering.VTable(ext_type.vtab_type))

# ______________________________________________________________________
# Validate Table Slot Types

def validate_type_table(table, comparer):
    """
    Determine the compatability of this table with its parents given an
    ordering.AbstractTable and a type compare function ((type1, type2) -> bool).
    """
    for parent in table.parents:
        for attr_name, attr_type in parent.attrdict.iteritems():
            type1 = table.attrdict[attr_name]
            if not comparer(type1, attr_type):
                raise error.NumbaError(
                    "Found incompatible slot for method or "
                    "attribute '%s':" % ())

def drop_self_type(type):
    if type.is_static:
        return type

    return type.return_type(*type.args[1:])

class AttributeTypeValidator(ExtTypeValidator):
    """
    Validate attribute types in the table with attribute types in the parent
    table.

    E.g. if attribute 'foo' has type 'double' in the base class, then
    it should also have type 'double' in the derived class.
    """

    def validate(self, ext_type):
        comparer = lambda t1, t2: t1 == t2
        validate_type_table(ext_type.attribute_table, comparer)


class MethodTypeValidator(ExtTypeValidator):
    """
    Validate method signatures in the vtable with method signatures
    in the parent table.
    """

    def validate(self, ext_type):
        def comparer(t1, t2):
            if t1.is_static and t2.is_static:
                return t1 == t2
            else:
                return drop_self_type(t1) == drop_self_type(t2)

        validate_type_table(ext_type.attribute_table, comparer)


# Validators that validate the vtab/attribute struct order
extending_order_validators = [
    AttributeTableOrderValidator(),
    MethodTableOrderValidator()
]

type_validators = [
    AttributeTypeValidator(),
    MethodTypeValidator(),
]

jit_type_validators = extending_order_validators + type_validators
autojit_type_validators = type_validators