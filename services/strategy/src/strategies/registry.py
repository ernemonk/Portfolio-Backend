"""
Strategy Registry
━━━━━━━━━━━━━━━━
Single source of truth for all registered strategies.
Import REGISTRY to access any strategy by name.
Add new strategies here — zero changes elsewhere.
"""
from .dca import DCAStrategy
from .grid import GridStrategy
from .ma_crossover import MACrossoverStrategy
from .momentum import MomentumStrategy

REGISTRY: dict = {
    "dca":          DCAStrategy(),
    "grid":         GridStrategy(),
    "momentum":     MomentumStrategy(),
    "ma_crossover": MACrossoverStrategy(),
}
