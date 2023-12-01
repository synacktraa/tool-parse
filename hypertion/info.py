from typing import Callable, Any
from pydantic import BaseModel

class FunctionInfo(BaseModel):
    obj: Callable[..., Any]
    description: str

class CriteriaInfo(BaseModel):
    description: str
    default: Any = None