from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from marznode.models import Inbound, Outbound


class User(BaseModel):
    id: int
    username: str
    key: str
    inbounds: list["Inbound"] = []
    outbounds: list["Outbound"] = []
