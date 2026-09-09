from __future__ import annotations
import re


def normalized_font_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


class FontRegistry:
    def __init__(self, faces):
        self.faces = faces

    def alias(self, family: str, weight: int | float | None) -> str | None:
        requested = normalized_font_name(family)
        candidates = [
            face
            for face in self.faces
            if requested in face["match_names"]
        ]
        if not candidates:
            return None
        requested_weight = int(weight) if isinstance(weight, (int, float)) else 400
        selected = min(
            candidates,
            key=lambda face: (abs(face["weight"] - requested_weight), face["weight"]),
        )
        return selected["alias"]
