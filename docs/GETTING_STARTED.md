# Getting Started with VirtuCast

## Overview

VirtuCast automates the creation of virtual news broadcasts using Unreal Engine 5, MetaHuman, and AI-powered tools.

## Prerequisites

### Required Software

1. **Unreal Engine 5.7+**
   - Download from Epic Games Launcher
   - Enable Python Editor Script Plugin

2. **Python 3.9+**
   - Install from python.org
   - Ensure pip is available

3. **MetaHuman**
   - Create account at metahuman.unrealengine.com
   - Download at least one MetaHuman character

4. **FFmpeg**
   - Required for video processing
   - Add to system PATH

### Optional

- CUDA-capable GPU for faster rendering
- Git for version control
- VideoCraft project (for TTS integration)

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/OldApeTalk/VirtuCast.git
cd VirtuCast
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Setup UE5 Project

1. Open Unreal Engine 5.7
2. Create new "Blank" project in `ue_project/` directory
3. Enable plugins:
   - Python Editor Script Plugin
   - MetaHuman Plugin
   - Live Link
   - Movie Render Queue

### 4. Configure Settings

Edit `config/default_config.yaml`:

```yaml
ue5:
  project_path: "path/to/your/project.uproject"
  editor_path: "path/to/UnrealEditor.exe"
```

## Quick Start Guide

### Step 1: Prepare News Script

Create a text file `my_news.txt`:

```
大家好，欢迎收看今天的新闻。
今天我们将为您报道最新的科技动态。
人工智能技术正在改变我们的生活...
```

### Step 2: Generate Video

```bash
python src/news_generator.py my_news.txt -o output/news.mp4
```

### Step 3: View Output

The generated video will be in `output/news.mp4`.

## Workflow

```
Text Script → TTS Audio → UE5 Control → MetaHuman → Render → Final Video
```

1. **Script Processing**: Parse and segment news script
2. **Audio Generation**: Convert text to speech (TTS)
3. **Subtitle Generation**: Create synchronized subtitles
4. **UE5 Automation**: Control MetaHuman and camera
5. **Rendering**: Export video from UE5
6. **Post-Processing**: Add subtitles, watermark, etc.

## Configuration

### Studio Themes

Available themes in `config/default_config.yaml`:
- `modern_news`: Contemporary news studio
- `classic_broadcast`: Traditional broadcast setup
- `minimal_tech`: Minimalist tech-style

### Camera Presets

Default sequence:
- Wide shot (3s)
- Medium shot (5s)
- Close-up (2s)

Customize in config file.

### MetaHuman Selection

Choose anchor in script or config:

```python
generator = NewsGenerator()
generator.set_anchor("FemaleAnchor01")
```

## Troubleshooting

### UE5 Not Found

Update `ue5.editor_path` in config file.

### Python Module Import Errors

Ensure UE5 Python Editor Plugin is enabled.

### VideoCraft Not Found

Update `videocraft.path` in config or install VideoCraft separately.

## Next Steps

- Read [Architecture](ARCHITECTURE.md) for technical details
- Check [API Documentation](API.md) for programming interface
- See [Examples](../examples/) for sample projects

## Support

- GitHub Issues: [VirtuCast Issues](https://github.com/OldApeTalk/VirtuCast/issues)
- Discussions: [VirtuCast Discussions](https://github.com/OldApeTalk/VirtuCast/discussions)
