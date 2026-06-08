from pydantic import BaseModel


class IdentityOut(BaseModel):
    identity: str
    type: str
    verification_status: str
    dkim_status: str = "N/A"
    dkim_signing: bool = False
