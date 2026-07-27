# Fusion 360 MCP - Multi-Model AI Integration

**FusionMCP** is a comprehensive Model Context Protocol (MCP) integration layer that connects Autodesk Fusion 360 with multiple AI backends (Ollama, OpenAI, Google Gemini, and Anthropic Claude) to enable AI-powered parametric CAD design through natural language.

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![Fusion 360](https://img.shields.io/badge/Fusion%20360-2025-orange)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

## 🎯 Features

- 🤖 **Multi-Model Support**: Seamlessly switch between Ollama, OpenAI GPT-4o, Google Gemini, and Claude 3.5
- 🔄 **Intelligent Routing**: Automatic fallback chain when primary model fails
- 📐 **Parametric Design**: AI understands and generates parametric CAD operations
- 🛡️ **Safety First**: Built-in validation for dimensions, units, and geometric feasibility
- 💾 **Context Caching**: Conversation and design state persistence (JSON/SQLite)
- 🎨 **Fusion 360 Integration**: Native add-in for seamless workflow
- ⚡ **Async Architecture**: Fast, non-blocking operations with retry logic
- 📊 **Structured Logging**: Detailed logs with Loguru

## 📋 Table of Contents

- [Architecture](#architecture)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Usage Examples](#usage-examples)
- [API Reference](#api-reference)
- [Model Comparison](#model-comparison)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Fusion 360 User                         │
│                           ↓                                 │
│              ┌─────────────────────────┐                    │
│              │  Fusion 360 Add-in      │                    │
│              │  - UI Dialog            │                    │
│              │  - Action Executor      │                    │
│              │  - Network Client       │                    │
│              └──────────┬──────────────┘                    │
│                         ↓ HTTP/REST                         │
│              ┌─────────────────────────┐                    │
│              │   MCP Server (FastAPI)  │                    │
│              │  - Router               │                    │
│              │  - Schema Validation    │                    │
│              │  - Context Cache        │                    │
│              └──────────┬──────────────┘                    │
│                         ↓                                    │
│         ┌───────────────┴───────────────────┐               │
│         ↓               ↓           ↓       ↓               │
│   ┌─────────┐   ┌──────────┐  ┌────────┐  ┌──────────┐     │
│   │ Ollama  │   │  OpenAI  │  │ Gemini │  │  Claude  │     │
│   │ (Local) │   │   API    │  │  API   │  │   API    │     │
│   └─────────┘   └──────────┘  └────────┘  └──────────┘     │
│                                                              │
│              System Prompt (FusionMCP Personality)          │
│              ↓                                              │
│         Structured JSON Actions → Fusion 360                │
└─────────────────────────────────────────────────────────────┘
```

### Component Overview

1. **Fusion 360 Add-in** (`fusion_addin/`)
   - Python-based Fusion 360 add-in
   - Captures user intent and design context
   - Executes structured CAD actions
   - Real-time UI feedback

2. **MCP Server** (`mcp_server/`)
   - FastAPI-based REST server
   - Routes requests to appropriate LLM
   - Validates and normalizes responses
   - Caches conversation history

3. **LLM Clients** (`mcp_server/llm_clients/`)
   - Unified interface for all models
   - Provider-specific implementations
   - Automatic retry and error handling

4. **System Prompt** (`prompts/system_prompt.md`)
   - Defines FusionMCP personality
   - Enforces JSON output format
   - Provides action schema templates

## 🚀 Installation

### Prerequisites

- **Python 3.11+** (for MCP server)
- **Autodesk Fusion 360** (2025 version recommended)
- **At least one LLM provider**:
  - [Ollama](https://ollama.ai) (local, free)
  - [OpenAI API Key](https://platform.openai.com)
  - [Google AI API Key](https://makersuite.google.com/app/apikey)
  - [Anthropic API Key](https://console.anthropic.com)

### Step 1: Clone Repository

```bash
git clone https://github.com/yourusername/fusion360-mcp.git
cd fusion360-mcp
```

### Step 2: Install Python Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Or install in development mode
pip install -e .
```

### Step 3: Configure Environment

Create `config.json` from example:

```bash
cp examples/example_config.json config.json
```

Edit `config.json` with your API keys:

```json
{
  "ollama_url": "http://localhost:11434",
  "openai_api_key": "sk-proj-...",
  "gemini_api_key": "AIza...",
  "claude_api_key": "sk-ant-...",
  "default_model": "openai:gpt-4o-mini",
  "mcp_host": "127.0.0.1",
  "mcp_port": 9000
}
```

**Alternative**: Use environment variables (`.env` file):

```bash
OPENAI_API_KEY=sk-proj-...
GEMINI_API_KEY=AIza...
CLAUDE_API_KEY=sk-ant-...
```

### Step 4: Install Fusion 360 Add-in

1. Copy `fusion_addin/` folder to Fusion 360 add-ins directory:
   - **Windows**: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`
   - **macOS**: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/`

2. Rename to `FusionMCP`:
   ```bash
   cp -r fusion_addin "/Users/YOUR_USER/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FusionMCP"
   ```

3. Restart Fusion 360

4. Open Fusion 360 → **Scripts and Add-Ins** → **Add-Ins** tab → Select **FusionMCP** → **Run**

## 🎬 Quick Start

### 1. Start MCP Server

```bash
# Activate virtual environment
source venv/bin/activate

# Start server
python -m mcp_server.server
```

Expected output:
```
INFO     | Logger initialized with level INFO
INFO     | Cache initialized: json
INFO     | System prompt loaded
INFO     | Initialized MCP Router with providers: ['ollama', 'openai', 'gemini', 'claude']
INFO     | MCP Server started on 127.0.0.1:9000
```

### 2. Test Server (Optional)

```bash
curl -X POST http://127.0.0.1:9000/mcp/command \
  -H "Content-Type: application/json" \
  -d '{
    "command": "ask_model",
    "params": {
      "provider": "openai",
      "model": "gpt-4o-mini",
      "prompt": "Create a 20mm cube"
    },
    "context": {
      "active_component": "RootComponent",
      "units": "mm",
      "design_state": "empty"
    }
  }'
```

### 3. Use in Fusion 360

1. Open Fusion 360
2. Click **Scripts and Add-Ins** → **Add-Ins** → **FusionMCP** → **Run**
3. Click **MCP Assistant** button in toolbar
4. Enter natural language command:
   - "Create a 20mm cube"
   - "Design a mounting bracket with 4 holes"
   - "Make a cylindrical shaft 10mm diameter, 50mm long"

## ⚙️ Configuration

### Full Configuration Options

```json
{
  // API Configuration
  "ollama_url": "http://localhost:11434",
  "openai_api_key": "sk-proj-...",
  "gemini_api_key": "AIza...",
  "claude_api_key": "sk-ant-...",

  // Model Selection
  "default_model": "openai:gpt-4o-mini",
  "fallback_chain": [
    "openai:gpt-4o-mini",
    "gemini:gemini-1.5-flash-latest",
    "ollama:llama3"
  ],

  // Server Settings
  "mcp_host": "127.0.0.1",
  "mcp_port": 9000,
  "allow_remote": false,

  // Logging
  "log_level": "INFO",
  "log_dir": "logs",

  // Caching
  "cache_enabled": true,
  "cache_type": "json",  // or "sqlite"
  "cache_path": "context_cache.json",

  // Timeouts and Retries
  "timeout_seconds": 30,
  "max_retries": 3,
  "retry_delay": 1.0,

  // Available Models
  "models": {
    "ollama": {
      "available": ["llama3", "mistral", "codellama"],
      "default": "llama3"
    },
    "openai": {
      "available": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
      "default": "gpt-4o-mini"
    },
    "gemini": {
      "available": ["gemini-1.5-pro-latest", "gemini-1.5-flash-latest"],
      "default": "gemini-1.5-flash-latest"
    },
    "claude": {
      "available": ["claude-3-5-sonnet-20241022"],
      "default": "claude-3-5-sonnet-20241022"
    }
  }
}
```

## 💡 Usage Examples

### Example 1: Simple Geometry

**Prompt**: "Create a 20mm cube"

**Generated Action**:
```json
{
  "action": "create_box",
  "params": {
    "width": 20,
    "height": 20,
    "depth": 20,
    "unit": "mm"
  },
  "explanation": "Creating a 20mm cubic box",
  "safety_checks": ["dimensions_positive", "units_valid"]
}
```

### Example 2: Complex Design

**Prompt**: "Design a mounting bracket 100x50mm with 4 M5 mounting holes"

**Generated Action Sequence**:
```json
{
  "actions": [
    {
      "action": "create_box",
      "params": {"width": 100, "height": 50, "depth": 5, "unit": "mm"},
      "explanation": "Create base plate"
    },
    {
      "action": "create_hole",
      "params": {"diameter": 5.5, "position": {"x": 10, "y": 10}, "unit": "mm"},
      "explanation": "M5 clearance hole (10mm edge offset)"
    },
    // ... 3 more holes
  ],
  "total_steps": 5
}
```

### Example 3: Parametric Design

**Prompt**: "Create a shaft with diameter 2x of length"

```json
{
  "clarifying_questions": [
    {
      "question": "What is the shaft length?",
      "context": "Need length to calculate diameter (diameter = 2 × length)",
      "suggestions": ["50mm", "100mm", "Custom"]
    }
  ]
}
```

## 📡 API Reference

### Endpoints

#### POST `/mcp/command`

Execute MCP command.

**Request Body**:
```json
{
  "command": "ask_model",
  "params": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "prompt": "User prompt here",
    "temperature": 0.7,
    "max_tokens": 2000
  },
  "context": {
    "active_component": "RootComponent",
    "units": "mm",
    "design_state": "empty"
  }
}
```

**Response**:
```json
{
  "status": "success",
  "message": "Action generated successfully",
  "actions_to_execute": [...],
  "llm_response": {...}
}
```

#### GET `/health`

Health check.

**Response**:
```json
{
  "status": "healthy",
  "providers": ["ollama", "openai", "gemini", "claude"],
  "cache_enabled": true
}
```

#### GET `/models`

List available models.

**Response**:
```json
{
  "models": {
    "ollama": ["llama3", "mistral"],
    "openai": ["gpt-4o", "gpt-4o-mini"],
    "gemini": ["gemini-1.5-pro-latest"],
    "claude": ["claude-3-5-sonnet-20241022"]
  }
}
```

#### GET `/history?limit=10`

Get conversation history.

**Response**:
```json
{
  "conversations": [...],
  "actions": [...]
}
```

### Supported Actions

| Action | Description | Required Params |
|--------|-------------|-----------------|
| `create_box` | Create rectangular box | `width`, `height`, `depth`, `unit` |
| `create_cylinder` | Create cylinder | `radius`, `height`, `unit` |
| `create_sphere` | Create sphere | `radius`, `unit` |
| `create_hole` | Create hole | `diameter`, `position`, `unit` |
| `extrude` | Extrude profile | `profile`, `distance`, `unit` |
| `fillet` | Round edges | `edges`, `radius`, `unit` |
| `apply_material` | Apply material | `material_name` |

## 🔬 Model Comparison

| Feature | Ollama (Local) | OpenAI GPT-4o | Google Gemini | Claude 3.5 |
|---------|---------------|---------------|---------------|------------|
| **Cost** | Free | $$ | $ | $$$ |
| **Speed** | Fast | Medium | Fast | Medium |
| **Offline** | ✅ Yes | ❌ No | ❌ No | ❌ No |
| **JSON Mode** | Limited | ✅ Native | Good | Good |
| **Reasoning** | Good | Excellent | Very Good | Excellent |
| **Geometry** | Good | Very Good | Excellent | Very Good |
| **Creative** | Good | Excellent | Very Good | Good |
| **Best For** | Privacy, Offline | Creative designs | Spatial reasoning | Safety validation |

### Recommended Workflows

1. **Creative Design**: OpenAI GPT-4o → Claude (validation)
2. **Geometric Precision**: Gemini → OpenAI
3. **Privacy-First**: Ollama (all tasks)
|4. **Cost-Optimized**: Gemini Flash → Ollama (fallback) |

| ## 📐 Plan Mode (preview before you build)

FusionMCP supports a **plan-then-confirm** flow so nothing is committed to
your design until you approve it.

**How it works**
1. Type a request in the **MCP Assistant** palette (e.g. *"A 100x50mm base
   plate with an M5 hole and a 40mm post"*).
2. Click **Preview Plan**. The server asks the LLM for proposed actions and
   builds a step-by-step **plan** plus a synthetic **3D preview PNG**
   (box = blue, cylinder = green tube, sphere = purple wireframe, hole =
   orange dashed ring). **No Fusion geometry is created yet.**
3. Review the schematic. Click **Execute** to build the real features via the
   Fusion add-in, or **Cancel** to discard.

The preview is a *synthetic plan sketch* (matplotlib), clearly distinct from the
final Fusion geometry — it is for judging the layout/sizes before committing.

**Endpoint / command**
- `POST /mcp/command` with `"command": "plan_action"` (same `params` +
  `context` shape as `ask_model`). Response `status` is `"planned"` and the
  `metadata_dict` carries `plan_text` and `preview_png` (base64 data-URI).
- The add-in's `MCPPalette.html` + `ui_dialog.py` already wire the palette
  buttons to this flow.



```
fusion360-mcp/
├── mcp_server/                 # MCP Server
│   ├── server.py              # FastAPI app
│   ├── router.py              # Request routing
│   ├── schema/                # Pydantic models
│   ├── llm_clients/           # LLM implementations
│   └── utils/                 # Utilities
├── fusion_addin/              # Fusion 360 Add-in
│   ├── main.py                # Entry point
│   ├── ui_dialog.py           # UI components
│   ├── fusion_actions.py      # Action executor
│   └── utils/network.py       # Network client
├── prompts/                   # System prompts
├── examples/                  # Example configs
├── tests/                     # Test suite
├── requirements.txt           # Dependencies
└── README.md                  # This file
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_mcp_server.py -v

# Run with coverage
pytest tests/ --cov=mcp_server --cov-report=html
```

### Adding New LLM Provider

1. Create client in `mcp_server/llm_clients/new_provider_client.py`:

```python
class NewProviderClient:
    async def generate(self, model, prompt, system_prompt, temperature, max_tokens):
        # Implementation
        return {
            "provider": "new_provider",
            "model": model,
            "output": "...",
            "json": {...},
            "tokens_used": 123
        }
```

2. Register in `router.py`:

```python
if config.new_provider_api_key:
    self.clients["new_provider"] = NewProviderClient(...)
```

### Code Style

- **PEP8** compliant
- **Type annotations** required
- **Docstrings** for all functions/classes
- **Async/await** for I/O operations

## 🐛 Troubleshooting

### Common Issues

#### 1. Server Won't Start

**Error**: `Address already in use`

**Solution**: Change port in `config.json`:
```json
{"mcp_port": 9001}
```

#### 2. Fusion Add-in Not Visible

**Solution**:
- Verify add-in is in correct folder
- Check `FusionMCP.manifest` exists
- Restart Fusion 360
- Check **Scripts and Add-Ins** → **Add-Ins** tab

#### 3. API Key Errors

**Error**: `401 Unauthorized`

**Solution**:
- Verify API key in `config.json`
- Check key has proper permissions
- Try environment variables instead

#### 4. Ollama Connection Failed

**Error**: `Connection refused`

**Solution**:
```bash
# Check Ollama is running
ollama list

# Start Ollama service
ollama serve
```

#### 5. JSON Parsing Errors

**Solution**:
- Check system prompt is loaded
- Verify model supports JSON mode
- Use temperature < 0.8 for better structure
- Enable `json_mode=True` in OpenAI client

### Debug Mode

Enable verbose logging:

```json
{"log_level": "DEBUG"}
```

Check logs in `logs/mcp_server.log`

### Health Check

```bash
# Check server health
curl http://127.0.0.1:9000/health

# List available models
curl http://127.0.0.1:9000/models

# View conversation history
curl http://127.0.0.1:9000/history?limit=5
```

## 🧪 Testing the System

### Manual CLI Test

```bash
curl -X POST http://127.0.0.1:9000/mcp/command \
  -H "Content-Type: application/json" \
  -d @examples/example_command.json
```

### Python Test Script

```python
import requests

command = {
    "command": "ask_model",
    "params": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "prompt": "Create a 10mm cube"
    },
    "context": {
        "units": "mm",
        "design_state": "empty"
    }
}

response = requests.post("http://127.0.0.1:9000/mcp/command", json=command)
print(response.json())
```

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

### Development Setup

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run linting
ruff check mcp_server/
black mcp_server/
```

## 📄 License

MIT License - see [LICENSE](LICENSE) file

## 🙏 Acknowledgments

- Autodesk Fusion 360 API
- FastAPI framework
- Anthropic, OpenAI, Google for LLM APIs
- Ollama for local LLM support

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/fusion360-mcp/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/fusion360-mcp/discussions)
- **Documentation**: [Wiki](https://github.com/yourusername/fusion360-mcp/wiki)

## 🗺️ Roadmap

- [ ] WebSocket streaming for real-time chat
- [ ] Multi-agent orchestration
- [ ] Generative Design API integration
- [ ] Geometry export to Markdown/docs
- [ ] Fusion 360 UI palette integration
- [ ] 3D preview before execution
- [ ] Undo/redo action history
- [ ] Cloud deployment support

---

**Built with ❤️ for the Fusion 360 and AI community**

---

## 🔌 Merged MCP add-in (FusionMCP) — dual-CAD, NOW SHIPPING

This repo ships a **standards-compliant MCP server add-in** that merges the
best of both upstreames AND adds a **Vectorworks backend**:

- **Protocol from Joe-Spencer/fusion-mcp-server** — a real `FastMCP` server
  (SSE @ `http://127.0.0.1:3000/sse`) so any MCP client (Claude
  Desktop, Cursor, Cline) connects, with no hardcoded paths and no
  debug-file spam.
- **Geometry from jaskirat1616/fusion360-mcp** — working `adsk` calls
  that actually BUILD parts: `create_box`, `create_cylinder`, `create_sphere`,
  `create_hole`, `apply_material`, plus `sketch`/`parameter` helpers.
- **Vectorworks backend** (NEW) — same action schema, same preview, but
  executed through the `vs.py` module. Vectorworks had **no public MCP
  server** (verified via GitHub search); this fills that gap with the exact
  architecture proven for Fusion.

It ALSO exposes the **plan-then-review** flow (`plan_design`): ask an LLM
for proposed actions, render a synthetic 3D preview PNG, return the plan
**without building anything** — execute only via the explicit geometry tools.

### Files
```
fusion_addin/
  run.py                  # Fusion 360 add-in entry: "FusionMCP" button starts server
  fusion_mcp_server.py   # FastMCP server: resources + tools + plan_design + backend switch
  fusion_geometry.py      # REAL adsk geometry calls (unit-aware)
  FusionMCP.manifest     # add-in manifest
vectorworks/
  run.py                  # Vectorworks entry: forces the vs.py backend
  vectorworks_geometry.py # REAL vs.py geometry calls (same action schema)
install_for_fusion.py     # installs mcp/matplotlib/numpy into Fusion's Python
```

### Install & run (auto-detecting — one server, two CAD apps)
1. `pip install -r requirements.txt`          (for local testing / preview)
2. `python install_for_fusion.py`            (puts mcp + matplotlib + numpy
                                             into Fusion 360's own Python;
                                             adapt the path for Vectorworks' Python)
3. **Fusion 360:** Scripts & Add-Ins → Add-Ins → + → select `fusion_addin/`
   → Run the **FusionMCP** command.
   **Vectorworks:** Scripts → Run Script → select `vectorworks/run.py`
   (or install as a plug-in).
4. Point your MCP client at `http://127.0.0.1:3000/sse`. The server
   auto-detects the host (adsk vs vs) and exposes `fusion://backend`
   so the client knows which app it is driving.
   - `plan_design("a 100x50mm base plate with an M5 hole")` → returns
     `plan_text` + `preview_png` (base64). Nothing is built.
   - `create_box(100, 50, 5, "mm")` → builds the real geometry
     in whichever CAD app is active.

### Wiring an LLM for plan_design
The add-in is provider-agnostic. In your loader, before starting the
server, register a callable:
```python
import fusion_addin.fusion_mcp_server as srv
srv.set_llm_callable(lambda prompt, system: my_llm(prompt, system))
```
The callable must return the model's raw JSON (an `{"actions":[...]}`
object). Leave it unset and `plan_design` returns an error while the
geometry tools still work standalone.

### Tests
- `tests/test_fusion_mcp_addin.py` — headless smoke test with stubbed `adsk`
  AND `vs` (under `tests/stubs/`): proves tools register, the Fusion
  backend drives the real adsk call chain (mm→cm), the Vectorworks backend
  drives the real `vs` call chain, and `plan_design` returns a plan +
  preview PNG on BOTH backends — all WITHOUT a live CAD instance.
