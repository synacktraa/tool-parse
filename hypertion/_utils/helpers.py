from enum import Enum, EnumMeta
from pydantic import BaseModel

from typing import Type, Any


SUPPORTED_TYPE_MAP = {
    str: 'string', int: 'integer', bool: 'boolean', list: 'list', dict: 'dictionary', Enum: 'string', BaseModel: 'object'
}
"""Supported types mapped schema types"""

SUPPORTED_TYPES = tuple(SUPPORTED_TYPE_MAP)
"""Supported types"""

SUPPORTED_TYPES_REPR = ', '.join(type_.__name__ for type_ in SUPPORTED_TYPES)
"""Supported types representation"""


def _construct_pydantic_field_map(model: Type[BaseModel], description: str):
    properties, required_fields = {}, []
    for field_name, field_info in model.model_fields.items():

        if field_info.annotation is model:
            raise RuntimeError(
                f"{field_name!r} field cannot have the same type as the Pydantic model '{model.__name__}'."
            )

        field_desc = field_info.description
        if field_desc is None:
            raise ValueError(f'{model.__name__!r} fields must have description.')
        
        default, annotation = field_info.default, field_info.annotation
        if field_info.is_required():
            required_fields.append(field_name)
        elif not isinstance(default, annotation):
            raise TypeError(
                f"{field_name!r} field is type-hinted as {annotation.__name__!r} but default value is of type {type(default).__name__!r}"
            )
        
        properties[field_name] = construct_property_map(
            annotation=annotation, description=field_desc
        )

    fields = {"type": "object", 'description': description, "properties": properties}
    if required_fields:
        fields['required'] = required_fields
    
    return fields

def construct_property_map(annotation, description: str):
    if issubclass(annotation, BaseModel):
        return _construct_pydantic_field_map(
            model=annotation, description=description
        ) 
    
    enum_map = {}
    if isinstance(annotation, EnumMeta):
        enum_map['enum'] = annotation._member_names_
        annotation = Enum
    elif annotation not in SUPPORTED_TYPES:
        raise TypeError(
            f"Only {SUPPORTED_TYPES_REPR!r} types are supported."
        ) 
    return {
        'type': SUPPORTED_TYPE_MAP[annotation], 'description': description, **enum_map
    }

def _forge_pydantic_model(model: Type[BaseModel], fields: dict[str, Any]):

    if not isinstance(fields, dict):
        raise ValueError(
            f"Couldn't parse {model.__name__!r} model fields."
        )
    final_fields = {}
    for field_name, field_info in model.model_fields.items():
        if field_name not in fields and field_info.default is None:
            raise KeyError(
                f"{model.__name__!r} model required field {field_name!r} missing."
            )
        final_fields[field_name] = forge_parameter(
            annotation=field_info.annotation, value=fields.get(field_name, field_info.default)
        )
    
    return model(**final_fields)
        

def forge_parameter(annotation: Type, value: Any):
    
    if issubclass(annotation, BaseModel):
        return _forge_pydantic_model(model=annotation, fields=value)

    if isinstance(annotation, EnumMeta):
        _enum = annotation._member_map_.get(value)
        if _enum is None:
            raise ValueError(
                f"{value!r} is not a valid {annotation.__name__!r} member." 
                f"Valid members: {annotation._member_names_!r}"
            )
        return _enum
    elif annotation not in SUPPORTED_TYPES:
        raise TypeError(
            f"Only {SUPPORTED_TYPES_REPR} types are supported."
        )
    if not isinstance(value, annotation):
        raise TypeError(
            f"Expected parameter type {annotation.__name__!r}, but received value of type {type(value)!r} instead."
        )
    return value