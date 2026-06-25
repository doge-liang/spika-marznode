from pydantic import BaseModel, Field


class Outbound(BaseModel):
    protocol: str
    address: str
    port: int
    username: str | None = None
    password: str | None = None
    inbound_tags: list[str] = Field(default_factory=list)


class NodeOutboundPolicy(BaseModel):
    id: int
    name: str
    protocol: str
    address: str
    port: int
    username: str | None = None
    password: str | None = None
    inbound_tags: list[str] = Field(default_factory=list)
