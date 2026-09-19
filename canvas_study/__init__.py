"""Shared application, discovery, indexing, and search core."""

from .application import CanvasApplication
from .index import ResourceIndex
from .registry import REGISTRY, ResourceRegistry

__all__ = ["CanvasApplication", "REGISTRY", "ResourceIndex", "ResourceRegistry"]
