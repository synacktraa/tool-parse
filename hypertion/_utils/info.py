from typing import Callable, Any

from pydantic import BaseModel

class FunctionInfo(BaseModel):
    memloc: Callable[..., Any]
    description: str

class CriteriaInfo(BaseModel):
    description: str
    default: Any = None