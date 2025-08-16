# distress_detection/__init__.py - Production Version
from .detector import DistressDetector, DistressLevel, DistressResult, get_detector, cleanup_detector

__all__ = [
    'DistressDetector', 
    'DistressLevel', 
    'DistressResult', 
    'get_detector', 
    'cleanup_detector'
]