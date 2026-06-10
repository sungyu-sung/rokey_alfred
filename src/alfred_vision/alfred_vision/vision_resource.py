import os
from pathlib import Path

DEFAULT_MODEL = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..', 'share',
    'alfred_vision', 'resource', 'best.pt'
)

CONF_THRESH  = 0.6
SNAPSHOT_DIR = Path('/tmp/detection_snapshots')
DEPTH_PATCH  = 4

ROBOT_ID_MAP = {
    '/robot2': 'robot2',
    '/robot4': 'robot4',
}
FLOOR_MAP = {
    '/robot2': 1,
    '/robot4': 2,
}
EVENT_TYPE_MAP = {
    'fire':    'FIRE',
    'patient': 'INJURED_PERSON',
    'pistol2': 'SUSPICIOUS_PERSON',
    'knife':   'SUSPICIOUS_PERSON',
    'wallet':  'LOST_ITEM',
    'bag':     'LOST_ITEM',
    'phone':   'LOST_ITEM',
}
EVENT_COLOR = {
    'FIRE':              (0,   60,  255),
    'INJURED_PERSON':    (0,   165, 255),
    'SUSPICIOUS_PERSON': (0,   255, 255),
    'LOST_ITEM':         (255, 200,   0),
}
