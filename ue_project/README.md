# VirtuCast UE5 Project

This directory will contain the Unreal Engine 5.7 project files.

## Setup Instructions

1. **Create New UE5 Project**:
   - Open Unreal Engine 5.7
   - Create new "Blank" project
   - Enable Python Editor Script Plugin
   - Save project in this directory

2. **Install Required Plugins**:
   - Python Editor Script Plugin (built-in)
   - MetaHuman Plugin
   - Live Link (for audio-driven animation)
   - Movie Render Queue

3. **Project Structure**:
   ```
   Content/
   ├── MetaHumans/        # MetaHuman characters
   ├── Studios/           # Virtual studio environments
   │   ├── Modern/
   │   ├── Classic/
   │   └── Minimal/
   ├── Cameras/           # Camera presets
   ├── Blueprints/        # Control blueprints
   ├── Sequences/         # Level sequences
   └── Materials/         # Custom materials
   ```

4. **Python Scripts** (see Scripts/ directory):
   - Scene setup automation
   - MetaHuman control
   - Camera management
   - Rendering pipeline

## Quick Start

After creating the UE5 project:

```python
# In UE5 Python console
import unreal
import sys
sys.path.append('d:/My_Prjs/VirtuCast/ue_project/Scripts')

import scene_builder
scene_builder.create_news_studio()
```

## Resources

- [UE5 Python API Documentation](https://docs.unrealengine.com/5.7/en-US/PythonAPI/)
- [MetaHuman Documentation](https://www.unrealengine.com/en-US/metahuman)
- [Sequencer Automation](https://docs.unrealengine.com/5.7/en-US/sequencer-python-api/)
