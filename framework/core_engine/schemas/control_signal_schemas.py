from typing import Literal

from pydantic import BaseModel, ConfigDict


class ControlSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_type: Literal[
        "backchannel",
        "potential_noise",
        "interruption",
    ]
