from pydantic import BaseModel


class Outbound(BaseModel):
    protocol: str
    address: str
    port: int
    username: str | None = None
    password: str | None = None
    inbound_tags: list[str] = []
