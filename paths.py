"""Project-root anchored path constants.

All default locations (config, data, chroma, logs) used to be CWD-relative,
which broke when the app was launched from any directory other than the
project root.  Anchoring them here (computed from __file__, not os.getcwd())
makes every default absolute regardless of the working directory.

Deliberately dependency-free (no config_loader / service imports) so every
module can import it without creating import cycles.

/ 锚定项目根目录的路径常量。原先各默认位置（配置、数据、向量库、日志）都
  依赖工作目录，从非项目根目录启动时会失效。此处基于 __file__ 计算绝对路径，
  使所有默认值不再依赖启动时的 CWD。

  本模块刻意保持零依赖（不 import config_loader / 任何 service），供所有模块
  安全引用而不会产生循环导入。
"""

import os
from pathlib import Path

# abspath (not resolve) keeps the same symlink semantics as app.py:101 and
# routers/misc.py:18, so log/scene directories do not drift under symlinks.
PROJECT_ROOT = Path(os.path.dirname(os.path.abspath(__file__)))

CONFIG_PATH = PROJECT_ROOT / "config.json"
CONFIG_TEMPLATE_PATH = PROJECT_ROOT / "config.template.json"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "defaultconfig.json"
DATA_DIR = PROJECT_ROOT / "data"
CHROMA_DIR = PROJECT_ROOT / "chroma_data"
LOGS_DIR = PROJECT_ROOT / "logs"
