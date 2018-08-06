import abc
import enum
from fractions import Fraction
from types import MappingProxyType
from typing import Callable, Any, List, Mapping, MutableMapping, Union
import warnings

import pandas
import xarray

import numpy as np
from rdata.parser._parser import RObject

from .. import parser


def convert_list(r_list: parser.RObject,
                 conversion_function: Callable=lambda x: x
                 ) -> Mapping[Union[str, bytes], Any]:
    """
    Expand a tagged R pairlist to a Python dictionary.

    Parameters
    ----------
    r_list: RObject
        Pairlist R object, with tags.
    conversion_function: Callable
        Conversion function to apply to the elements of the list. By default
        is the identity function.

    Returns
    -------
    dictionary: dict
        A dictionary with the tags of the pairwise list as keys and their
        corresponding values as values.

    See Also
    --------
    convert_vector

    """
    if r_list.info.type is parser.RObjectType.NILVALUE:
        return {}
    elif r_list.info.type is not parser.RObjectType.LIST:
        raise TypeError("Must receive a LIST or NILVALUE object")

    if r_list.tag is None:
        raise NotImplementedError("Lists are assumed to have tags")
    else:
        tag = conversion_function(r_list.tag)

    cdr = conversion_function(r_list.value[1])
    if cdr is None:
        cdr = {}

    return {tag: conversion_function(r_list.value[0]), **cdr}


def convert_attrs(r_obj: parser.RObject,
                  conversion_function: Callable=lambda x: x
                  ) -> Mapping[Union[str, bytes], Any]:
    """
    Return the attributes of an object as a Python dictionary.

    Parameters
    ----------
    r_obj: RObject
        R object.
    conversion_function: Callable
        Conversion function to apply to the elements of the attribute list. By
        default is the identity function.

    Returns
    -------
    dictionary: dict
        A dictionary with the names of the attributes as keys and their
        corresponding values as values.

    See Also
    --------
    convert_list

    """
    if r_obj.attributes:
        attrs = conversion_function(r_obj.attributes)
    else:
        attrs = {}
    return attrs


def convert_vector(r_vec: parser.RObject,
                   conversion_function: Callable=lambda x: x,
                   attrs: Mapping[Union[str, bytes], Any]=None
                   ) -> Union[List[Any], Mapping[Union[str, bytes], Any]]:
    """
    Convert a R vector to a Python list or dictionary.

    If the vector has a ``names`` attribute, the result is a dictionary with
    the names as keys. Otherwise, the result is a Python list.

    Parameters
    ----------
    r_vec: RObject
        R vector.
    conversion_function: Callable
        Conversion function to apply to the elements of the vector. By default
        is the identity function.

    Returns
    -------
    vector: dict or list
        A dictionary with the ``names`` of the vector as keys and their
        corresponding values as values. If the vector does not have an argument
        ``names``, then a normal Python list is returned.

    See Also
    --------
    convert_list

    """
    if attrs is None:
        attrs = {}

    if r_vec.info.type is not parser.RObjectType.VEC:
        raise TypeError("Must receive a VEC object")

    value: Any = [conversion_function(o) for o in r_vec.value]

    # If it has the name attribute, use a dict instead
    field_names = attrs.get('names')
    if field_names:
        value = dict(zip(field_names, value))

    return value


def convert_char(r_char: parser.RObject) -> Union[str, bytes]:
    """
    Decode a R character array to a Python string or bytes.

    The bits that signal the encoding are in the general pointer. The
    string can be encoded in UTF8, LATIN1 or ASCII, or can be a sequence
    of bytes.

    Parameters
    ----------
    r_char: RObject
        R character array.

    Returns
    -------
    string: str or bytes
        Decoded string.

    See Also
    --------
    convert_symbol

    """
    if r_char.info.type is not parser.RObjectType.CHAR:
        raise TypeError("Must receive a CHAR object")

    if r_char.info.gp & parser.CharFlags.UTF8:
        return r_char.value.decode("utf_8")
    elif r_char.info.gp & parser.CharFlags.LATIN1:
        return r_char.value.decode("latin_1")
    elif r_char.info.gp & parser.CharFlags.ASCII:
        return r_char.value.decode("ascii")
    elif r_char.info.gp & parser.CharFlags.BYTES:
        return r_char.value
    else:
        raise NotImplementedError("Encoding not implemented")


def convert_symbol(r_symbol: parser.RObject,
                   conversion_function: Callable=lambda x: x
                   ) -> Union[str, bytes]:
    """
    Decode a R symbol to a Python string or bytes.

    Parameters
    ----------
    r_symbol: RObject
        R symbol.
    conversion_function: Callable
        Conversion function to apply to the char element of the symbol.
        By default is the identity function.

    Returns
    -------
    string: str or bytes
        Decoded string.

    See Also
    --------
    convert_char

    """
    if r_symbol.info.type is parser.RObjectType.SYM:
        return conversion_function(r_symbol.value)
    else:
        raise TypeError("Must receive a SYM object")


def convert_array(r_array: RObject,
                  conversion_function: Callable=lambda x: x,
                  attrs: Mapping[Union[str, bytes], Any]=None
                  ) -> Union[np.ndarray, xarray.DataArray]:
    """
    Convert a R array to a Numpy ndarray or a Xarray DataArray.

    If the array has attribute ``dimnames`` the output will be a
    Xarray DataArray, preserving the dimension names.

    Parameters
    ----------
    r_array: RObject
        R array.
    conversion_function: Callable
        Conversion function to apply to the attributes of the array.
        By default is the identity function.

    Returns
    -------
    array: ndarray or DataArray
        Array.

    See Also
    --------
    convert_vector

    """
    if attrs is None:
        attrs = {}

    if r_array.info.type not in {parser.RObjectType.INT,
                                 parser.RObjectType.REAL}:
        raise TypeError("Must receive an array object")

    value = r_array.value

    shape = attrs.get('dim')
    if shape is not None:
        value = np.reshape(value, shape)

    dimnames = attrs.get('dimnames')
    if dimnames:
        dimension_names = ["dim_" + str(i) for i, _ in enumerate(dimnames)]
        coords = {dimension_names[i]: d
                  for i, d in enumerate(dimnames) if d is not None}

        value = xarray.DataArray(value, dims=dimension_names, coords=coords)

    return value


def dataframe_constructor(obj, attrs):
    return pandas.DataFrame(obj)


def factor_constructor(obj, attrs):
    factor = enum.Enum('Factor', [(l, l) for l in attrs['levels']])

    def __eq__(self, other):
        if isinstance(other, type(self)):
            return self is other
        else:
            if self.value == other:
                return True
            else:
                value = getattr(other, "value", NotImplemented)
                if value is not NotImplemented:
                    return self.value == value
                else:
                    return False

    def __hash_(self):
        return hash(self.value)

    factor.__eq__ = __eq__
    factor.__hash__ = __hash_

    return [factor(attrs['levels'][i - 1]) for i in obj]


def ts_constructor(obj, attrs):

    start, end, frequency = attrs['tsp']

    frequency = int(frequency)

    real_start = Fraction(int(round(start * frequency)), frequency)
    real_end = Fraction(int(round(end * frequency)), frequency)

    index = np.arange(real_start, real_end + Fraction(1, frequency),
                      Fraction(1, frequency))

    if frequency == 1:
        index = index.astype(int)

    return pandas.Series(obj, index=index)


default_class_map_dict = {
    "data.frame": dataframe_constructor,
    "factor": factor_constructor,
    "ts": ts_constructor,
}

DEFAULT_CLASS_MAP = MappingProxyType(default_class_map_dict)


class Converter(abc.ABC):

    @abc.abstractmethod
    def convert(self, data: Union[parser.RData, parser.RObject]) -> Any:
        pass


class SimpleConverter(Converter):

    def __init__(self,
                 constructor_dict: Mapping[
                     Union[str, bytes],
                     Callable[[Any, Mapping], Any]]=None) -> None:
        self.references: MutableMapping[int, Any] = {}

        self.constructor_dict = (DEFAULT_CLASS_MAP
                                 if constructor_dict is None
                                 else constructor_dict)

    def convert(self, data: Union[parser.RData, parser.RObject]) -> Any:
        """
        Convert a R object to a Python one.
        """

        obj: RObject
        if isinstance(data, parser.RData):
            obj = data.object
        else:
            obj = data

        attrs = convert_attrs(obj, self.convert)

        reference_id = id(obj)

        # Return the value if previously referenced
        value: Any = self.references.get(id(obj))
        if value is not None:
            pass

        if obj.info.type == parser.RObjectType.SYM:

            # Return the internal string
            value = convert_symbol(obj, self.convert)

        elif obj.info.type == parser.RObjectType.LIST:

            # Expand the list and process the elements
            value = convert_list(obj, self.convert)

        elif obj.info.type == parser.RObjectType.CHAR:

            # Return the internal string
            value = convert_char(obj)

        elif obj.info.type == parser.RObjectType.INT:

            # Return the internal array
            value = convert_array(obj, self.convert, attrs=attrs)

        elif obj.info.type == parser.RObjectType.REAL:

            # Return the internal array
            value = convert_array(obj, self.convert, attrs=attrs)

        elif obj.info.type == parser.RObjectType.STR:

            # Convert the internal strings
            value = [self.convert(o) for o in obj.value]

        elif obj.info.type == parser.RObjectType.VEC:

            # Convert the internal objects
            value = convert_vector(obj, self.convert, attrs=attrs)

        elif obj.info.type == parser.RObjectType.REF:

            # Return the referenced value
            value = self.references.get(id(obj.referenced_object))
            # value = self.references[id(obj.referenced_object)]
            if value is None:
                reference_id = id(obj.referenced_object)
                value = self.convert(obj.referenced_object)

        elif obj.info.type == parser.RObjectType.NILVALUE:

            value = None

        else:
            raise NotImplementedError(f"Type {obj.info.type} not implemented")

        if obj.info.object:
            classname = attrs["class"]
            assert len(classname) == 1
            classname = classname[0]

            constructor = self.constructor_dict.get(classname, None)

            if constructor:
                new_value = constructor(value, attrs)
            else:
                new_value = NotImplemented

            if new_value is NotImplemented:
                warnings.warn(f"Missing constructor for R class "
                              f"\"{classname}\". "
                              f"The underlying R object is returned instead",
                              stacklevel=1)
            else:
                value = new_value

        self.references[reference_id] = value

        return value


def convert(data, *args, **kwargs):
    """
    Uses the default converter to convert the data.

    """
    return SimpleConverter(*args, **kwargs).convert(data)