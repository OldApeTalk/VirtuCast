# VirtuCast

🎙️ **AI-Powered Virtual News Broadcasting System with Unreal Engine 5 & MetaHuman**

VirtuCast is an automated virtual news studio that combines cutting-edge technologies to generate professional news broadcasts with AI-driven MetaHuman anchors.

## ✨ Features

- 🎭 **MetaHuman Integration**: Realistic virtual news anchors powered by Unreal Engine 5.7
- 🤖 **AI-Driven Automation**: Text-to-Speech (TTS) with facial animation synchronization
- 🎬 **Professional Studio**: Virtual broadcasting environment with dynamic camera controls
- 📝 **Script Processing**: Automatic subtitle generation and video composition
- 🔄 **Complete Pipeline**: From text script to final rendered video
- 🎨 **Customizable**: Multiple studio themes, camera presets, and anchor configurations

## 🏗️ Architecture

```
Text Script → TTS Audio → UE5 Python Control → MetaHuman Performance → Render → Final Video
```

## 🚀 Getting Started

### Prerequisites

- Unreal Engine 5.7+
- Python 3.9+
- MetaHuman Creator account
- CUDA-capable GPU (recommended)

### Installation

```bash
# Clone the repository
git clone https://github.com/OldApeTalk/VirtuCast.git
cd VirtuCast

# Install Python dependencies
pip install -r requirements.txt

# Configure UE5 project (see docs)
```

## 📦 Project Structure

```
VirtuCast/
├── ue_project/          # Unreal Engine 5 project
│   ├── Content/
│   │   ├── MetaHumans/
│   │   ├── Studios/     # Virtual studio environments
│   │   └── Blueprints/
│   └── Scripts/         # UE Python automation scripts
├── src/                 # Python control layer
│   ├── news_generator.py
│   ├── ue_connector.py
│   └── videocraft_bridge.py
├── templates/           # Studio templates and presets
└── config/              # Configuration files
```

## 🎯 Roadmap

- [x] Project initialization
- [ ] UE5 Python API integration
- [ ] MetaHuman audio-driven animation
- [ ] Virtual studio scene builder
- [ ] Multi-camera system
- [ ] Complete automation pipeline
- [ ] Template library
- [ ] Web UI control panel

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details

## 🙏 Acknowledgments

- Built on [VideoCraft](https://github.com/OldApeTalk/VideoCraft) foundation
- Powered by Unreal Engine 5.7
- MetaHuman technology by Epic Games

## 📧 Contact

- GitHub: [@OldApeTalk](https://github.com/OldApeTalk)
- Issues: [VirtuCast Issues](https://github.com/OldApeTalk/VirtuCast/issues)

---

⭐ Star this project if you find it interesting!
