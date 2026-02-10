# BITS Whisperer — Product Requirements Document

> **Version:** 1.0.0 - **Updated:** 2026-02-08 - **Status:** Implementation
> Complete
>
> Developed by **Blind Information Technology Solutions (BITS)**

______________________________________________________________________

## 1. Purpose & Vision

**BITS Whisperer** is a consumer-grade WXPython desktop application for audio
transcription. It targets Windows and macOS users who need reliable
speech-to-text without technical expertise — journalists, students, researchers,
accessibility advocates, and content creators.

### Design Pillars

| Pillar               | Description                                                                                                                                                              |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Accessible**       | WCAG 2.1/2.2 adapted for desktop; menu bar primary interface; full keyboard + screen reader support                                                                      |
| **Private**          | Local transcript storage by default; API keys in OS credential store; offline-capable providers                                                                          |
| **Versatile**        | 17 transcription providers (cloud + local); 14 Whisper models; 7 export formats; Auphonic audio post-production                                                          |
| **Simple**           | Consumer-friendly defaults; Basic mode hides advanced controls and unactivated providers; first-run setup wizard with experience mode selection; one-click transcription |
| **Background-aware** | System tray integration; balloon notifications; minimize-to-tray for long batches                                                                                        |
| **Cross-platform**   | Windows 10+ and macOS 12+; CUDA and Apple Silicon Metal GPU detection                                                                                                    |

______________________________________________________________________

## 2. Target Users

| Persona             | Pain Point                               | BITS Whisperer Solution                                   |
| ------------------- | ---------------------------------------- | --------------------------------------------------------- |
| **Journalist**      | Needs accurate transcripts of interviews | Batch processing, speaker diarization, auto-export        |
| **Student**         | Lecture recordings on a budget           | Free local Whisper models, simple mode                    |
| **Researcher**      | Large datasets of recordings             | Folder import, concurrent workers, background mode        |
| **Content Creator** | Episode transcripts for SEO & subtitles  | SRT/VTT export, multiple providers for quality comparison |

______________________________________________________________________

## 3. Whisper Models (Local Inference)

14 model variants via **faster-whisper** on CPU or CUDA GPU:

| Model                | Params | Disk   | Min RAM | Min VRAM | Speed  | Accuracy | Languages    |
| -------------------- | ------ | ------ | ------- | -------- | ------ | -------- | ------------ |
| Tiny                 | 39 M   | 75 MB  | 2 GB    | CPU-OK   | 5 of 5 | 2 of 5   | 99           |
| Tiny (English)       | 39 M   | 75 MB  | 2 GB    | CPU-OK   | 5 of 5 | 2 of 5   | English only |
| Base                 | 74 M   | 142 MB | 2 GB    | CPU-OK   | 4 of 5 | 3 of 5   | 99           |
| Base (English)       | 74 M   | 142 MB | 2 GB    | CPU-OK   | 4 of 5 | 3 of 5   | English only |
| Small                | 244 M  | 466 MB | 4 GB    | 2 GB     | 3 of 5 | 4 of 5   | 99           |
| Small (English)      | 244 M  | 466 MB | 4 GB    | 2 GB     | 3 of 5 | 4 of 5   | English only |
| Medium               | 769 M  | 1.5 GB | 8 GB    | 4 GB     | 2 of 5 | 4 of 5   | 99           |
| Medium (English)     | 769 M  | 1.5 GB | 8 GB    | 4 GB     | 2 of 5 | 5 of 5   | English only |
| Large v1             | 1.55 B | 3 GB   | 12 GB   | 6 GB     | 1 of 5 | 5 of 5   | 99           |
| Large v2             | 1.55 B | 3 GB   | 12 GB   | 6 GB     | 1 of 5 | 5 of 5   | 99           |
| Large v3             | 1.55 B | 3 GB   | 12 GB   | 6 GB     | 1 of 5 | 5 of 5   | 99           |
| Large v3 Turbo       | 809 M  | 1.6 GB | 8 GB    | 4 GB     | 3 of 5 | 5 of 5   | 99           |
| Distil Large v2 (EN) | 756 M  | 1.5 GB | 8 GB    | 4 GB     | 4 of 5 | 4 of 5   | English only |
| Distil Large v3 (EN) | 756 M  | 1.5 GB | 8 GB    | 4 GB     | 4 of 5 | 4 of 5   | English only |

The **Model Manager** (Ctrl+M) downloads models from HuggingFace and shows
hardware eligibility -- models are tagged as eligible, cautioned, or ineligible
based on the user's CPU, RAM, and GPU detected via `DeviceProbe`.

______________________________________________________________________

## 4. Transcription Providers

17 adapters implementing `TranscriptionProvider` ABC:

| #   | Provider              | Module                     | Type  | Rate/min | Key Required | Highlights                                                                                       |
| --- | --------------------- | -------------------------- | ----- | -------- | ------------ | ------------------------------------------------------------------------------------------------ |
| 1   | Local Whisper         | `local_whisper.py`         | Local | Free     | No           | Offline, private, GPU-accelerated                                                                |
| 2   | Windows Speech        | `windows_speech.py`        | Local | Free     | No           | SAPI5 + WinRT, offline (Windows only)                                                            |
| 3   | Azure Embedded Speech | `azure_embedded.py`        | Local | Free     | No           | Microsoft neural models, offline                                                                 |
| 4   | OpenAI Whisper        | `openai_whisper.py`        | Cloud | $0.006   | Yes          | Fast, reliable, verbose timestamps                                                               |
| 5   | ElevenLabs Scribe     | `elevenlabs_provider.py`   | Cloud | $0.005   | Yes          | 99+ languages, best-in-class accuracy                                                            |
| 6   | Groq Whisper          | `groq_whisper.py`          | Cloud | $0.003   | Yes          | 188x real-time on LPU hardware                                                                   |
| 7   | AssemblyAI            | `assemblyai_provider.py`   | Cloud | $0.011   | Yes          | Speaker labels, auto-chapters                                                                    |
| 8   | Deepgram Nova-2       | `deepgram_provider.py`     | Cloud | $0.013   | Yes          | Smart formatting, fast streaming                                                                 |
| 9   | Azure Speech Services | `azure_speech.py`          | Cloud | $0.017   | Yes          | 100+ languages, continuous recognition                                                           |
| 10  | Google Speech-to-Text | `google_speech.py`         | Cloud | $0.024   | Yes          | Diarization, enhanced models                                                                     |
| 11  | Google Gemini         | `gemini_provider.py`       | Cloud | $0.0002  | Yes          | Cheapest cloud, multimodal AI                                                                    |
| 12  | Amazon Transcribe     | `aws_transcribe.py`        | Cloud | $0.024   | Yes          | S3 integration, medical vocabularies                                                             |
| 13  | Rev.ai                | `rev_ai_provider.py`       | Cloud | $0.020   | Yes          | Human-hybrid option, high accuracy                                                               |
| 14  | Speechmatics          | `speechmatics_provider.py` | Cloud | $0.017   | Yes          | 50+ languages, real-time streaming                                                               |
| 15  | Vosk                  | `vosk_provider.py`         | Local | Free     | No           | Lightweight offline ASR (Kaldi). 20+ languages, 40-50 MB models. Works on very low-end hardware. |
| 16  | Parakeet              | `parakeet_provider.py`     | Local | Free     | No           | NVIDIA NeMo high-accuracy English ASR. 600M–1.1B param models.                                   |
| 17  | Auphonic              | `auphonic_provider.py`     | Cloud | ~$0.01   | Yes          | Audio post-production + Whisper transcription                                                    |

### Provider Selection

The `ProviderManager` maintains a registry of all adapters. The user selects a
provider in Settings, Provider tab. API keys are stored and retrieved via
`KeyStore` (backed by `keyring` / Windows Credential Manager). The
`TranscriptionService` resolves keys automatically at runtime — including
composite keys for AWS (access key + secret key + region).

### Cloud Provider Onboarding

Cloud providers must be **activated** before they appear in Basic mode. The
`AddProviderDialog` (Tools, then Add Provider) guides the user through a
three-step workflow:

1. **Select** a cloud provider from the 12 available options
1. **Enter** the required API key (and any auxiliary credentials like AWS
   region)
1. **Validate** the key with a live test API call

On successful validation, the provider's key is stored in `KeyStore`, and its
identifier is added to `GeneralSettings.activated_providers`. In Basic mode,
only local providers and activated cloud providers appear in the provider
dropdown. In Advanced mode, all providers are visible regardless of activation.

Each cloud provider's `validate_api_key()` method makes a real API call:

| Provider       | Validation Method                                |
| -------------- | ------------------------------------------------ |
| OpenAI         | `client.models.list()`                           |
| Google Speech  | `ListOperations` via service account credentials |
| Azure Speech   | Silent WAV `recognize_once()`                    |
| Groq           | `client.models.list()`                           |
| Deepgram       | `GET /v1/projects`                               |
| AssemblyAI     | `GET /v2/transcript?limit=1`                     |
| AWS Transcribe | `list_transcription_jobs(MaxResults=1)`          |
| Gemini         | `genai.list_models()`                            |
| Rev.ai         | `client.get_account()`                           |
| Speechmatics   | `GET /v2/jobs?limit=1`                           |
| ElevenLabs     | `GET /v1/models`                                 |
| Auphonic       | `GET /api/user.json`                             |

### Auphonic Integration

Auphonic provides professional cloud-based audio post-production with built-in
speech recognition. BITS Whisperer integrates Auphonic both as:

1. **Transcription Provider** (`AuphonicProvider`): Creates an Auphonic
   production, applies audio algorithms, runs Whisper speech recognition, and
   returns the transcript.
1. **Standalone Audio Service** (`AuphonicService`): Processes audio through
   Auphonic's algorithms without transcription — useful as a cloud-based
   preprocessing step.

#### Auphonic API Capabilities

| Capability                   | Description                                                      |
| ---------------------------- | ---------------------------------------------------------------- |
| **Adaptive Leveler**         | Corrects level differences between speakers, music, and speech   |
| **Loudness Normalization**   | Target LUFS (-16 podcast, -23 broadcast, -24 TV US)              |
| **Noise & Hum Reduction**    | Automatic detection; configurable amount (3-100 dB)              |
| **Filtering**                | High-pass, auto-EQ, bandwidth extension                          |
| **Silence & Filler Cutting** | Remove silences, filler words, coughs, music segments            |
| **Intro/Outro**              | Automatically prepend/append audio/video segments                |
| **Chapter Marks**            | Import/export chapter marks for enhanced podcasts                |
| **Audio Inserts**            | Insert audio segments at specific offsets (dynamic ad insertion) |
| **Speech Recognition**       | Built-in Whisper or external (Google, Amazon, Speechmatics)      |
| **Automatic Shownotes**      | AI-generated summaries, tags, and chapters (paid feature)        |
| **Multitrack**               | Process multi-speaker recordings with per-track settings         |
| **Output Formats**           | MP3, AAC, FLAC, WAV, Opus, Vorbis, ALAC, video                   |
| **Publishing**               | Export to Dropbox, SoundCloud, YouTube, FTP, SFTP, S3, etc.      |
| **Presets**                  | Save and reuse processing configurations                         |
| **Webhooks**                 | HTTP POST callbacks when processing completes                    |
| **Cuts**                     | Manual cut regions with start/end times                          |
| **Fade In/Out**              | Configurable fade time (0–5000 ms)                               |

#### Auphonic Authentication

| Method                  | Use Case                         | Details                                        |
| ----------------------- | -------------------------------- | ---------------------------------------------- |
| **API Key**             | Personal scripts, BITS Whisperer | Bearer token from Account Settings page        |
| **HTTP Basic Auth**     | Simple scripts                   | Username + password (not recommended for apps) |
| **OAuth 2.0 (Web)**     | Third-party web applications     | Client ID/Secret + redirect URI + grant code   |
| **OAuth 2.0 (Desktop)** | Desktop/mobile apps              | Client ID/Secret + username/password exchange  |

BITS Whisperer uses **API Key authentication**. The user generates a token at
<https://auphonic.com/accounts/settings/#api-key> and stores it via the
Providers & Keys settings tab. The key is persisted in `KeyStore` (Windows
Credential Manager) as `"auphonic"` to `"Auphonic API Token"`.

#### Auphonic Pricing

| Plan          | Recurring Credits | One-Time Credits | Cost       |
| ------------- | ----------------- | ---------------- | ---------- |
| Free          | 2 hours/month     | None             | $0         |
| Starter       | 9 hours/month     | None             | $11/month  |
| Professional  | 45 hours/month    | None             | $49/month  |
| Enterprise    | Custom            | Custom           | Contact    |
| Pay-as-you-go | None              | Purchased blocks | ~$0.01/min |

#### Auphonic API Endpoints

| Endpoint                                   | Method   | Purpose                              |
| ------------------------------------------ | -------- | ------------------------------------ |
| `/api/user.json`                           | GET      | Account info & credits               |
| `/api/productions.json`                    | POST     | Create production                    |
| `/api/production/{uuid}.json`              | GET      | Get/update production details        |
| `/api/production/{uuid}/upload.json`       | POST     | Upload audio/image files             |
| `/api/production/{uuid}/start.json`        | POST     | Start audio processing               |
| `/api/production/{uuid}/status.json`       | GET      | Poll production status               |
| `/api/production/{uuid}/publish.json`      | POST     | Publish to outgoing services         |
| `/api/simple/productions.json`             | POST     | Simple API (one-shot upload+process) |
| `/api/presets.json`                        | GET/POST | List/create presets                  |
| `/api/preset/{uuid}.json`                  | GET      | Get preset details                   |
| `/api/services.json`                       | GET      | List external services               |
| `/api/info/algorithms.json`                | GET      | Available audio algorithms           |
| `/api/info/output_files.json`              | GET      | Available output formats             |
| `/api/info/production_status.json`         | GET      | Status code reference                |
| `/api/download/audio-result/{uuid}/{file}` | GET      | Download processed files             |

### Provider-Specific Settings

Each cloud provider exposes its unique configurable options during onboarding
via the Add Provider dialog. Settings are stored in `ProviderDefaultSettings`
and applied automatically via the `configure()` method before each
transcription.

| Provider      | Configurable Settings                                                                                                |
| ------------- | -------------------------------------------------------------------------------------------------------------------- |
| Auphonic      | Leveler, loudness target, noise/hum reduction, silence/filler/cough cutting, speech engine, output format, crosstalk |
| Deepgram      | Model (nova-2/nova/enhanced/base), smart format, punctuation, paragraphs, utterances                                 |
| AssemblyAI    | Punctuation, formatting, auto chapters, content safety, sentiment analysis, entity detection                         |
| Google Speech | Recognition model, max speaker count                                                                                 |
| Azure         | Custom endpoint ID                                                                                                   |
| AWS           | Max speaker labels                                                                                                   |
| Speechmatics  | Operating point (enhanced/standard)                                                                                  |
| ElevenLabs    | Timestamp granularity (segment/word)                                                                                 |
| OpenAI        | Model, temperature                                                                                                   |
| Groq          | Model (v3-turbo/v3/distil)                                                                                           |
| Gemini        | Model (2.0-flash/1.5-flash/1.5-pro)                                                                                  |
| Rev.ai        | Skip diarization                                                                                                     |

### AI Services (Translation, Summarization & Chat)

The `AIService` class (in `core/ai_service.py`) provides translation and
summarization of transcripts via **6 pluggable AI providers**:

| #   | Provider       | Module/Class          | Models                                                   | Notes                                      |
| --- | -------------- | --------------------- | -------------------------------------------------------- | ------------------------------------------ |
| 1   | OpenAI         | `OpenAIAIProvider`    | gpt-4o, gpt-4o-mini                                      | Fastest, most reliable                     |
| 2   | Anthropic      | `AnthropicAIProvider` | Claude Sonnet 4, Claude Haiku                            | Strong for long transcripts                |
| 3   | Azure OpenAI   | `AzureOpenAIProvider` | Configurable deployment                                  | Enterprise-grade, GDPR compliant           |
| 4   | Google Gemini  | `GeminiAIProvider`    | Gemini 2.0 Flash, 1.5 Flash/Pro                          | Fast, affordable                           |
| 5   | GitHub Copilot | `CopilotAIProvider`   | gpt-4o (via Copilot SDK)                                 | Interactive chat & tool-augmented          |
| 6   | Ollama         | `OllamaAIProvider`    | Any Ollama/GGUF model (Llama, Mistral, Gemma, Phi, etc.) | Local, free, private — no API key required |

AI features are accessed via the **AI** menu:

- **Translate** (Ctrl+T): Translates the transcript to the configured target
  language (or multiple languages simultaneously)
- **Summarize** (Ctrl+Shift+S): Generates concise, detailed, or bullet-point
  summaries
- **Copilot Chat** (Ctrl+Shift+C): Opens the interactive chat panel for Q&A
- **AI Action Builder**: Opens the template editor for creating
  post-transcription AI processing templates
- **AI Provider Settings**: Configures AI providers (6 providers including
  Ollama)

AI provider settings (`AISettings` dataclass) include:

- `selected_provider` (openai/anthropic/azure_openai/gemini/copilot/ollama)
- `openai_model`, `anthropic_model`, `gemini_model`, `copilot_model`,
  `ollama_model`
- `ollama_endpoint`, `ollama_custom_model`
- `temperature`, `max_tokens`
- `translation_language`, `summarization_style`
- `multi_target_languages` — list of languages for simultaneous translation
- `custom_vocabulary` — domain-specific terms for improved AI accuracy
- `active_translation_template`, `active_summarization_template` — selected
  prompt template IDs
- `custom_prompt_templates` — user-defined prompt templates
- `context_strategy` — transcript fitting strategy
  (smart/truncate/tail/head_tail)
- `context_transcript_budget_pct` — fraction of context window for transcript
  (default 0.70)
- `context_response_reserve_tokens` — tokens reserved for AI response (default
  4096\)
- `context_max_conversation_turns` — max conversation turns to keep (default 20)

### AI Model Catalog

The `constants.py` module defines a comprehensive AI model catalog with
real-time pricing information via the `AIModelInfo` frozen dataclass:

| Field                 | Type  | Description                                    |
| --------------------- | ----- | ---------------------------------------------- |
| `id`                  | str   | Model identifier                               |
| `name`                | str   | Display name                                   |
| `provider`            | str   | Provider key (openai/anthropic/gemini/copilot) |
| `description`         | str   | Human-readable description                     |
| `input_price_per_1m`  | float | USD per 1M input tokens (0 = included)         |
| `output_price_per_1m` | float | USD per 1M output tokens (0 = included)        |
| `context_window`      | int   | Maximum context tokens                         |
| `max_output_tokens`   | int   | Maximum output tokens                          |
| `copilot_tier`        | str   | Required Copilot tier (empty if not Copilot)   |
| `is_premium`          | bool  | Requires premium Copilot subscription          |
| `supports_streaming`  | bool  | Whether the model supports streaming           |

#### Model Counts by Provider

| Provider  | Count  | Models                                                                                       |
| --------- | ------ | -------------------------------------------------------------------------------------------- |
| OpenAI    | 4      | GPT-4o Mini, GPT-4o, GPT-4 Turbo, GPT-3.5 Turbo                                              |
| Anthropic | 3      | Claude Sonnet 4, Claude Haiku 4, Claude 3.5 Sonnet                                           |
| Gemini    | 8      | Gemini 2.0 Flash, 2.5 Pro, 2.5 Flash + Gemma 27B/12B/4B/1B/3n-E4B                            |
| Copilot   | 7      | GPT-4o Mini, GPT-4o, GPT-4 Turbo, Claude Sonnet 4, Claude Haiku 4, o3-mini, Gemini 2.0 Flash |
| **Total** | **22** | All models across all providers                                                              |

Helper functions: `get_ai_model_by_id()`, `get_models_for_provider()`,
`get_copilot_models_for_tier()`, `format_price_per_1k()`.

### Copilot Subscription Tiers

Copilot models are gated by subscription tier via `COPILOT_TIERS`:

| Tier       | Price          | Available Models                                         |
| ---------- | -------------- | -------------------------------------------------------- |
| Free       | $0             | GPT-4o Mini                                              |
| Pro        | $10/month      | All 7 models including premium (Claude, o3-mini, Gemini) |
| Business   | $19/user/month | All Pro models + organization admin controls             |
| Enterprise | $39/user/month | All models + knowledge bases, fine-tuning, compliance    |

The `CopilotSettings.subscription_tier` field (default: "pro") controls which
models appear in the model selector. `get_copilot_models_for_tier()` returns
only models at or below the user's tier level.

### Prompt Templates

10 built-in prompt templates (`BUILTIN_PROMPT_TEMPLATES`) via the
`PromptTemplate` frozen dataclass:

| Field         | Type | Description                                             |
| ------------- | ---- | ------------------------------------------------------- |
| `id`          | str  | Template identifier                                     |
| `name`        | str  | Display name                                            |
| `category`    | str  | translation / summarization / analysis                  |
| `description` | str  | Human-readable description                              |
| `template`    | str  | Prompt text with `{text}` and `{language}` placeholders |
| `is_builtin`  | bool | True for built-in, False for user-created               |

#### Template Breakdown

| Category      | Count | Templates                                                         |
| ------------- | ----- | ----------------------------------------------------------------- |
| Translation   | 4     | Standard, Informal, Technical, Legal                              |
| Summarization | 4     | Concise Summary, Detailed Summary, Bullet Points, Meeting Minutes |
| Analysis      | 2     | Sentiment Analysis, Extract Questions                             |

Active templates are tracked in `AISettings.active_translation_template` and
`AISettings.active_summarization_template`. Users can also create custom
templates stored in `AISettings.custom_prompt_templates`.

Helper functions: `get_prompt_template_by_id()`, `get_templates_by_category()`.

### Custom Vocabulary

`AISettings.custom_vocabulary` stores a list of domain-specific terms (acronyms,
proper nouns, technical jargon) that are injected into AI prompts to improve
translation and summarization accuracy. The vocabulary is appended to the prompt
context before sending to the AI provider.

### Multi-Language Simultaneous Translation

`AISettings.multi_target_languages` stores a list of target language codes.
`AIService.translate_multi()` iterates over each language and calls
`translate()` independently, returning a dict mapping each language to its
`AIResponse`. This enables one-click translation to multiple languages.

### Real-Time Streaming Transcription

The `ProviderCapabilities.supports_streaming` field indicates whether a
transcription provider supports real-time streaming:

| Provider   | Streaming |
| ---------- | :-------: |
| Deepgram   |    Yes    |
| AssemblyAI |    Yes    |
| All others |    No     |

### GitHub Copilot SDK Integration

The `CopilotService` class (in `core/copilot_service.py`) integrates the GitHub
Copilot SDK for interactive AI-powered transcript analysis:

#### CopilotService

- **Async SDK client** with process management for the Copilot CLI
- **Session management** — conversation history maintained per session
- **Streaming responses** — real-time token-by-token response delivery
- **Custom tools** — transcript-aware tools that let the agent access and
  analyze the current transcript
- **Agent configuration** — name, instructions, persona, and welcome message
- **CLI detection** — auto-detects `github-copilot-cli` on PATH or manual path

#### Interactive AI Chat Panel (`ui/copilot_chat_panel.py`)

- **Toggle**: Ctrl+Shift+C or AI, then Copilot Chat
- **Streaming display** — responses appear token-by-token
- **Quick actions** — one-click buttons for common tasks (summarize, key points,
  speakers, action items)
- **Transcript context** — automatically provides the current transcript to the
  agent
- **New conversation** — clear history and start fresh
- **Slash commands** — 28 built-in `/commands` for AI analysis (summarize,
  translate, key-points, action-items, topics, speakers, search, ask, run, copy)
  and app actions (help, clear, status, provider, export, open, start, pause,
  cancel, clear-queue, retry, settings, live, models, agent, history,
  open-folder, context)
- **Autocomplete** — `wx.PopupTransientWindow` appears as the user types `/`,
  with keyboard navigation (Up/Down/Tab/Enter/Escape)

#### Slash Command System (`ui/slash_commands.py`)

Extensible registry of chat commands with:

- **`SlashCommand` dataclass** — name, description, category, handler, aliases,
  arg_hint, requires_transcript
- **`SlashCommandRegistry`** — register/get/match (prefix + substring
  autocomplete), categories, alias resolution
- **`parse_slash_command()`** — regex parser for `/command args` input
- **`build_default_registry()`** — factory returning 28 built-in commands in two
  categories (AI, App)

#### Copilot Setup Wizard (`ui/copilot_setup_dialog.py`)

Four-step guided setup dialog:

1. **CLI Install** — Checks for GitHub Copilot CLI; offers WinGet install on
   Windows
1. **SDK Install** — Installs the Copilot SDK Python package
1. **Authentication** — Authenticates with GitHub via CLI device flow
1. **Test** — Runs a connection test to verify everything works

#### Document Reader (`core/document_reader.py`)

Utility module that extracts plain text from multiple file formats for use as AI
context. Supports plain text (.txt, .md, .csv, .log, .json, .xml, .yaml), Word
documents (.docx via python-docx), spreadsheets (.xlsx/.xls via openpyxl), PDF
(.pdf via pypdf), and RTF (.rtf via striprtf). Enforces a 10 MB file size limit
and provides graceful fallbacks when optional libraries are not installed.

#### AI Action Builder (`ui/agent_builder_dialog.py`)

Five-tab guided dialog for creating reusable post-transcription AI processing
templates. Templates define system prompts, model parameters, processing goals,
and document attachments that are automatically applied after transcription
completes.

| Tab              | Purpose                                                                                                     |
| ---------------- | ----------------------------------------------------------------------------------------------------------- |
| **Identity**     | Action name, description                                                                                    |
| **Instructions** | System prompt with 8 built-in presets                                                                       |
| **Tools**        | Enable/disable transcript-aware tools                                                                       |
| **Welcome**      | Set the greeting message for the chat panel                                                                 |
| **Attachments**  | Attach reference documents (glossaries, style guides, etc.) to provide additional context for AI processing |

8 built-in presets:

| Preset            | Description                                            |
| ----------------- | ------------------------------------------------------ |
| Meeting Minutes   | Formal minutes with attendees, decisions, action items |
| Action Items      | Extract to-do items, deadlines, and responsibilities   |
| Executive Summary | Brief overview for leadership/stakeholders             |
| Interview Notes   | Key points, themes, and notable quotes                 |
| Lecture Notes     | Educational content structured for study               |
| Q&A Extraction    | Questions and answers identified and paired            |
| General Assistant | General-purpose transcript analysis                    |
| Custom            | Blank template for custom instructions                 |

Templates are saved as JSON files in `DATA_DIR/agents/` using the `AgentConfig`
dataclass from `copilot_service.py`. The `AgentConfig` includes an
`attachments: list[Attachment]` field for document attachments. Each
`Attachment` has `file_path`, `instructions` (per-attachment guidance), and
`display_name` fields with full serialization support.

### AI Actions (Post-Transcription Processing)

AI Actions allow automatic AI processing of transcripts immediately after
transcription completes. The feature works with any configured AI provider
(OpenAI, Anthropic, Azure OpenAI, Gemini, Copilot, or Ollama).

#### Pipeline Integration

After a job completes transcription (Step 5 in the pipeline), the service checks
`job.ai_action_template`. If set, it:

1. Sets `job.ai_action_status = "running"`
1. Resolves the template instructions (built-in preset or saved file)
1. Reads document attachments via `_build_attachments_text()` using
   `DocumentReader` (extracts text from DOCX, PDF, XLSX, RTF, TXT, and other
   formats; 10 MB size limit)
1. Fits the transcript to the model's context window using
   `ContextWindowManager` (smart strategy auto-selects truncate or head+tail
   based on overflow ratio; attachment tokens are accounted for in the budget,
   reducing transcript space proportionally)
1. Lazy-imports `AIService` and calls `provider.generate()`
1. Stores the result in `job.ai_action_result` or error in `job.ai_action_error`
1. Updates `job.ai_action_status` to "completed" or "failed"

#### Job Model Fields

| Field                   | Type       | Description                                                          |
| ----------------------- | ---------- | -------------------------------------------------------------------- |
| `ai_action_template`    | str        | Built-in preset name or path to AgentConfig JSON                     |
| `ai_action_result`      | str        | Output text from AI processing                                       |
| `ai_action_status`      | str        | "", "running", "completed", "failed"                                 |
| `ai_action_error`       | str        | Error message if processing failed                                   |
| `ai_action_attachments` | list[dict] | Per-job attachment overrides (file_path, instructions, display_name) |

#### Built-in Presets (6)

| Preset            | Instructions Summary                                    |
| ----------------- | ------------------------------------------------------- |
| Meeting Minutes   | Formal meeting minutes with attendees and action items  |
| Action Items      | Extract tasks, deadlines, and assigned responsibilities |
| Executive Summary | Brief overview highlighting key points and decisions    |
| Interview Notes   | Key discussion points, themes, and notable quotes       |
| Lecture Notes     | Structured educational notes for study and review       |
| Q&A Extraction    | Identify and pair all questions with their answers      |

#### User Interface

- **AddFileWizard**: AI Action dropdown with "None (transcribe only)" + built-in
  presets + saved templates (prefixed with ★)
- **Queue Panel**: Status indicators — ⭐ (pending), ⏳ (running), ✓ (completed),
  ✗ (failed)
- **Transcript Panel**: AI Action result section below the transcript with
  label, text area, and Copy button. Dynamically shown/hidden based on job
  status.
- **Main Frame**: AI action status announced to screen readers; transcript panel
  auto-refreshes on completion

### Context Window Management

The `ContextWindowManager` class (in `core/context_manager.py`) provides
model-aware token budgeting for all AI interactions — chat, AI actions, and
slash commands. It replaces the previous hardcoded 50,000-character truncation
with intelligent, per-model context allocation.

#### Token Estimation

| Method                      | Approach                                               |
| --------------------------- | ------------------------------------------------------ |
| `estimate_tokens()`         | Heuristic: `len(text) / chars_per_token` (default 4.0) |
| `estimate_tokens_precise()` | Exact: tiktoken encoding (OpenAI models only)          |
| `count_tokens()`            | Unified: tries tiktoken first, falls back to heuristic |

#### Model Context Window Lookup

`get_model_context_window(model, provider)` resolves context sizes:

1. Exact match in `AIModelInfo` catalog (22+ models with known context windows)
1. Heuristic fallback for unknown models (e.g., GPT-4 → 128K, Claude → 200K,
   Gemini → 1M, Ollama → 8K)
1. Ultimate fallback: 16,000 tokens

#### Transcript Fitting Strategies

| Strategy    | Behavior                                                      |
| ----------- | ------------------------------------------------------------- |
| `truncate`  | Keep the beginning of the transcript (previous default)       |
| `tail`      | Keep the end — useful for recent context                      |
| `head_tail` | Keep beginning and end, elide middle with marker              |
| `smart`     | Auto-selects: truncate if overflow ≤1.3×, head_tail otherwise |

#### Context Budget Allocation

`prepare_chat_context()` orchestrates the full budget:

1. Looks up model context window
1. Subtracts response reserve (default 4,096 tokens)
1. Estimates system prompt token cost
1. Allocates transcript budget (default 70% of remaining)
1. Fits transcript using the configured strategy
1. Trims conversation history (max turns + remaining token budget)
1. Returns `PreparedContext` with budget breakdown

`prepare_action_context()` handles one-shot AI actions with the same budget
logic but no conversation history. It accepts an optional `attachments_text`
parameter; when provided, attachment tokens are subtracted from the available
budget before fitting the transcript.

#### Settings

| Field                             | Type  | Default | Description                       |
| --------------------------------- | ----- | ------- | --------------------------------- |
| `context_strategy`                | str   | "smart" | Fitting strategy                  |
| `context_transcript_budget_pct`   | float | 0.70    | Fraction of window for transcript |
| `context_response_reserve_tokens` | int   | 4096    | Tokens reserved for response      |
| `context_max_conversation_turns`  | int   | 20      | Max conversation turns kept       |

#### Integration Points

- `ai_service.py` `chat()` — uses `prepare_chat_context()` for multi-turn chat
- `copilot_service.py` `_create_session()` — fits transcript for Copilot
  sessions
- `transcription_service.py` `_run_ai_action()` — fits transcript for
  post-transcription actions; `_build_attachments_text()` reads document
  attachments via `DocumentReader`
- `slash_commands.py` `/summarize` and `/run` — fits transcript for slash
  command execution
- `copilot_chat_panel.py` — displays context budget in status bar (e.g.,
  "Context: 45K/128K tokens (35%)")
- `/context` slash command — shows detailed budget breakdown in chat

#### CopilotSettings Dataclass (11 fields)

| Field                    | Type | Default                     |
| ------------------------ | ---- | --------------------------- |
| `enabled`                | bool | False                       |
| `cli_path`               | str  | "" (auto-detect)            |
| `use_logged_in_user`     | bool | True                        |
| `default_model`          | str  | "gpt-4o"                    |
| `streaming`              | bool | True                        |
| `system_message`         | str  | Transcript assistant msg    |
| `agent_name`             | str  | "BITS Transcript Assistant" |
| `agent_instructions`     | str  | ""                          |
| `auto_start_cli`         | bool | True                        |
| `allow_transcript_tools` | bool | True                        |
| `chat_panel_visible`     | bool | False                       |

### Speaker Diarization

Speaker diarization (identifying who spoke when) is supported through two
mechanisms:

#### Cloud Provider Diarization

10 cloud providers support built-in diarization when "Include speaker labels" is
enabled:

| Provider          | Max Speakers | Implementation                                         |
| ----------------- | ------------ | ------------------------------------------------------ |
| Azure Speech      | Configurable | `ConversationTranscriber` with `speaker_id` extraction |
| Google Speech     | Configurable | `diarization_config` on recognition request            |
| Deepgram          | Auto         | Nova-2 `diarize=true` parameter                        |
| AssemblyAI        | Auto         | `speaker_labels=True` feature                          |
| Amazon Transcribe | Configurable | `ShowSpeakerLabels` in settings                        |
| ElevenLabs        | Auto         | Built-in `diarize` parameter                           |
| Rev.ai            | Auto         | Automatic speaker detection                            |
| Speechmatics      | Auto         | Speaker change detection                               |
| Google Gemini     | Auto         | Multimodal speaker detection                           |
| Auphonic          | n/a          | Post-production only (no diarization)                  |

#### Cloud-Free Local Diarization (`core/diarization.py`)

Optional privacy-first speaker detection using **pyannote.audio**:

- **`LocalDiarizer`** class wraps `pyannote.audio.Pipeline` with lazy loading
- **`diarize(audio_path, min_speakers, max_speakers)`** returns
  `list[SpeakerTurn]`
- **`apply_to_transcript(result, turns)`** merges diarization with transcription
  segments by temporal overlap
- **`apply_speaker_map(result, speaker_map)`** renames speakers
  post-transcription
- Requires HuggingFace auth token for gated models (stored in `KeyStore`)
- Works as post-processing on ANY provider's output

Configuration via `DiarizationSettings`:

- `enabled` (default True), `max_speakers` (10), `min_speakers` (2)
- `use_local_diarization` (False), `local_engine` ("pyannote")
- `pyannote_model` ("pyannote/speaker-diarization-3.1")
- `speaker_map` (dict mapping internal IDs to display names)

#### Speaker Editing (Post-Transcription)

The transcript panel provides speaker management after transcription:

- **Manage Speakers** button opens `SpeakerRenameDialog` with editable name
  fields for all detected speakers (e.g., rename "Speaker 1" to "Alice")
- **Right-click context menu** on any transcript line offers "Assign to Speaker"
  submenu and "New Speaker..." option
- **Display format**: `[timestamp]  SpeakerName: text` for natural reading
- **Instant global updates** -- all renames applied immediately to the full
  transcript via the `speaker_map` on `TranscriptionResult`

______________________________________________________________________

## 5. Audio Preprocessing Pipeline

A 7-filter ffmpeg filter chain applied before transcoding to maximise speech
recognition accuracy (`AudioPreprocessor` class):

| #   | Filter                   | Default | ffmpeg Filter         | Purpose                         |
| --- | ------------------------ | ------- | --------------------- | ------------------------------- |
| 1   | High-pass (80 Hz)        | On      | `highpass=f=80`       | Remove low-frequency rumble     |
| 2   | Low-pass (8 kHz)         | On      | `lowpass=f=8000`      | Cut high-frequency hiss         |
| 3   | Noise gate (-40 dB)      | On      | `agate`               | Suppress background noise       |
| 4   | De-esser (5 kHz)         | Off     | `equalizer`           | Reduce sibilance                |
| 5   | Dynamic range compressor | On      | `acompressor`         | Even out volume levels          |
| 6   | Loudness normalisation   | On      | `loudnorm` (EBU R128) | Standardise to -16 LUFS         |
| 7   | Silence trimming         | On      | `silenceremove`       | Remove leading/trailing silence |

All filter parameters (frequency, threshold, ratio, attack, release) are
user-configurable via the Settings, Audio Processing tab (Advanced Mode only).
The preprocessor is skipped if ffmpeg is not available — the transcoder handles
the fallback path.

______________________________________________________________________

## 6. Audio Format Support

12 input formats detected by file extension:

```text
MP3, WAV, OGG, Opus, FLAC, M4A, AAC, WebM, WMA, AIFF, AMR, MP4
```

All files are transcoded to 16 kHz mono WAV (`pcm_s16le`) before being sent to
the provider for consistent results across all engines.

______________________________________________________________________

## 7. Batch & Folder Processing

- **File, Add Files** (Ctrl+O): Multi-select file dialog with audio-type filter.
  Opens the **AddFileWizard** for per-file configuration (provider, model,
  language, custom name, AI Action selection). The wizard includes an **Audio
  Preview** tool for single-file imports, with pitch-preserving speed control
  and optional clip-range selection.
- **File, Add Folder** (Ctrl+Shift+O): Recursively scans a folder for supported
  audio files. Shows cost estimation for cloud providers with a confirmation
  dialog before processing begins.
- **Concurrent workers**: Configurable (default: 2). Each worker picks from a
  shared `queue.Queue` and runs preprocess, transcode, then transcribe.
- **Limits** (configurable in Advanced Settings):
  - Max file size: 500 MB
  - Max duration: 4 hours
  - Max batch files: 100
  - Max batch size: 10 GB
  - Chunk duration: 30 min (with 2 s overlap)
- **Pause / Resume** (F6): Pauses the queue; active jobs continue.
- **Cancel Selected** (Delete): Cancels a single job.
- **Clear Queue** (Ctrl+Shift+Del): Removes all unstarted jobs.
- **Clear Completed**: Removes finished jobs from the queue (Queue menu or
  toolbar).
- **Retry All Failed**: Re-queues all failed jobs (Queue menu or toolbar).
- **Retry Selected**: Re-queues a single failed or cancelled job (context menu).
- **Rename** (F2): Rename the selected file or folder with a custom display
  name.

### Budget Limits

`BudgetSettings` (in `core/settings.py`) provides per-provider and per-model
spending limits for cloud transcription:

| Field                 | Type  | Default | Description                             |
| --------------------- | ----- | ------- | --------------------------------------- |
| `enabled`             | bool  | True    | Enable budget tracking                  |
| `default_limit`       | float | 0.0     | Default per-batch limit (0 = unlimited) |
| `provider_limits`     | dict  | {}      | Per-provider or per-model limits        |
| `always_confirm_paid` | bool  | True    | Show confirmation for paid providers    |

Budget limits are checked before batch processing starts. If estimated cost
exceeds the configured limit, a confirmation dialog is shown. Provider-specific
and model-specific limits override the default.

### Cost Estimation

Cloud provider costs are estimated before transcription begins using per-minute
rates from the provider table. The `AddFileWizard` and folder import dialog
display estimated costs. Cost estimation uses audio duration (detected via
pydub/ffprobe) with a file-size-based fallback for files that can't be probed.

### Queue Panel (`ui/queue_panel.py`)

The queue panel uses a `wx.TreeCtrl` with hierarchical folder grouping:

- **TreeView layout**: Files are grouped under collapsible folder nodes when
  added from directories. Root-level files appear at the top level.
- **Folder nodes**: Show folder name, file count, and aggregated status summary
  (e.g., "3 files — 2 completed, 1 pending")
- **Item display**: Each file shows display name, provider, status, cost
  estimate, progress percentage, and AI Action indicators
- **AI Action indicators**: ⭐ (pending action), ⏳ (running), ✓ (completed), ✗
  (failed)
- **Toolbar**: Filter/search bar, Clear Completed button, Retry All Failed
  button
- **Filter/search**: Real-time text filter above the tree; matches file name,
  custom name, provider, status, and folder name. Case-insensitive.
- **Context menus**: Right-click files for Rename, Retry, Cancel, Remove, Change
  Provider/Model/Language, AI Action, Properties; right-click folders for
  Rename, Set AI Action for Pending, Remove Folder, Expand/Collapse
- **Drag and drop**: Drop audio files directly onto the queue panel
- **Keyboard shortcuts**: F2 (Rename), Delete (Cancel/Remove), F5 (Start)

### Custom Job Naming

Jobs and folders support custom display names:

- `Job.custom_name: str` — User-assigned name for a transcription job
- `Job.display_name` property — Returns `custom_name` if set, else `file_name`,
  else derived from `file_path`
- Renamed via F2 keyboard shortcut, context menu, or inline during AddFileWizard
- Custom names appear in the queue panel, transcript panel, exports, and
  Properties dialog
- Folder custom names are tracked separately in
  `QueuePanel._folder_custom_names`

______________________________________________________________________

## 8. Background Processing & System Tray

### System Tray Icon (`ui/tray_icon.py`)

A `wx.adv.TaskBarIcon` that provides background-mode support:

| Feature                   | Description                                                     |
| ------------------------- | --------------------------------------------------------------- |
| **Tray icon**             | Programmatic 16x16 "B" icon; always present when app is running |
| **Tooltip progress**      | Shows "Transcribing X/Y (Z%)" or "Idle" on hover                |
| **Left-click**            | Toggle window visibility (show/hide)                            |
| **Right-click menu**      | Show/Hide • Pause/Resume • Progress summary • Quit              |
| **Balloon notifications** | Job complete, batch complete, and error notifications           |

### Minimize to Tray

- **View, Minimize to System Tray** (default: on): When enabled, closing the
  window hides it to the tray instead of quitting. Processing continues.
- The **close** button and **Alt+F4** hide the window; the tray context menu's
  **Quit** item is the true exit.
- When a batch completes while minimised, the app restores itself automatically.
- `EVT_ICONIZE` also hides to tray on minimize.

### Notifications

- **Balloon/toast**: Job completion, batch completion, and error notifications
  appear via `ShowBalloon()` when the window is hidden.
- A **system bell** (`wx.Bell()`) sounds on batch completion.
- Notification settings (enable/disable, sound on/off) configurable in Settings,
  General, Behaviour section.

______________________________________________________________________

## 9. Output & Export

### 7 Export Formats

| Format     | Module           | Extension | Timestamps | Diarization |
| ---------- | ---------------- | --------- | ---------- | ----------- |
| Plain Text | `plain_text.py`  | `.txt`    | Optional   | Optional    |
| Markdown   | `markdown.py`    | `.md`     | Yes        | Yes         |
| HTML       | `html_export.py` | `.html`   | Yes        | Yes         |
| Word       | `word_export.py` | `.docx`   | Yes        | Yes         |
| SRT        | `srt.py`         | `.srt`    | Required   | No          |
| VTT        | `vtt.py`         | `.vtt`    | Required   | No          |
| JSON       | `json_export.py` | `.json`   | Yes        | Yes         |

### Auto-Export on Completion

When enabled (**View, Auto-Export on Completion**), each completed transcript is
automatically saved as a `.txt` file alongside the source audio file. If a file
with the same name exists, a numeric suffix is appended (e.g.,
`interview_1.txt`, `interview_2.txt`).

______________________________________________________________________

## 10. User Interface

### Layout

```text
Layout:
  Top:      Menu Bar (File, Queue, View, Tools, Help)
  Left:     Queue Panel (file list)
  Right:    Transcript Panel (viewer / editor)
  Bottom:   Status Bar [status] [progress gauge] [hw]
```

### Menu Structure

#### File

- Add Files… (Ctrl+O)
- Add Folder… (Ctrl+Shift+O)
- Recent Files (numbered list, Clear Recent Files)
- Export Transcript… (Ctrl+E)
- Exit (Alt+F4)

#### Queue

- Start Transcription (F5)
- Pause (F6)
- Cancel Selected (Delete)
- Clear Queue (Ctrl+Shift+Del)

#### View

- Advanced Mode (Ctrl+Shift+A) — toggle check item
- Minimize to System Tray — toggle check item (default: on)
- Auto-Export on Completion — toggle check item (default: off)

#### Tools

- Settings… (Ctrl+,)
- Manage Models… (Ctrl+M)
- Audio Preview… (Ctrl+Shift+P)
- Add Provider…
- Copilot Setup…
- Hardware Info…
- View Log…

#### AI

- Translate (Ctrl+T)
- Summarize (Ctrl+Shift+S)
- Copilot Chat (Ctrl+Shift+C)
- AI Action Builder…
- AI Provider Settings…

#### Help

- Setup Wizard…
- Check for Updates…
- Learn more about BITS
- About… (F1)

### Settings Dialog (9 tabs)

| Tab                  | Visibility    | Contents                                                                                                                       |
| -------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **General**          | Always        | Provider selection, language, timestamps, diarization, Behaviour section (minimize-to-tray, auto-export, notifications, sound) |
| **Transcription**    | Always        | Timestamps, speakers, confidence, word-level, segmentation, VAD, temperature, beam size, compute type                          |
| **Output**           | Always        | Default export format, output directory, filename template, encoding                                                           |
| **Playback**         | Always        | Audio preview speed range, step size, and jump timing                                                                          |
| **Providers & Keys** | Always        | API key entry per provider with Test button validation                                                                         |
| **Paths & Storage**  | Always        | Output dir, models dir, temp dir, log file                                                                                     |
| **AI Providers**     | Always        | AI provider selection (5 providers), model selection, temperature, max tokens, translation language, summarization style       |
| **Audio Processing** | Advanced Mode | All 7 preprocessing filter toggles & parameters                                                                                |
| **Advanced**         | Advanced Mode | Max file size, duration, batch limits, concurrency, chunking, GPU, log level                                                   |

### Simple vs Advanced Mode

- **Basic Mode** (default): Shows General, Transcription, Output, Providers &
  Keys, Paths & Storage, and AI Providers tabs. Audio Processing and Advanced
  tabs are hidden. Only local providers and **activated** cloud providers appear
  in the provider dropdown. Cloud providers must be activated via the Add
  Provider wizard before they become available. Sensible defaults are applied
  automatically.
- **Advanced Mode** (Ctrl+Shift+A): Reveals all 8 settings tabs. All cloud
  providers appear in the provider dropdown regardless of activation status.
  Full control over audio preprocessing, GPU settings, concurrency, and chunking
  parameters.
- **Experience Mode Setting**: Persisted in `settings.json` as
  `general.experience_mode` ("basic" or "advanced"). Set during the Setup Wizard
  or toggled via View, then Advanced Mode.

### Recent Files

- Persisted to `DATA_DIR/recent_files.json` (max 10 entries).
- Accessible via File, Recent Files submenu with numbered mnemonics (&1 ...).
- Clear Recent Files option at the bottom.
- Non-existent files are silently removed when selected.

______________________________________________________________________

## 11. Self-Update System

`core/updater.py` implements GitHub Releases-based update checking:

1. **Startup check**: Silent background check 3 seconds after launch. If a newer
   version exists, the status bar shows a notification.
1. **Manual check**: Help, Check for Updates opens a dialog with version
   comparison and a link to the release page.
1. **Version comparison** uses `packaging.version.Version` for correct semver.
1. **No auto-install** — the user downloads the new version manually.

______________________________________________________________________

## 12. Architecture

### File Tree

```text
src/bits_whisperer/
  __main__.py              # Entry point
  app.py                   # wx.App subclass
  core/
    transcription_service.py  # Job queue, workers, orchestration
    provider_manager.py       # Provider registry & routing
    audio_preprocessor.py     # 7-filter ffmpeg preprocessing chain
    audio_player.py           # Audio preview playback (ffmpeg + sounddevice)
    dependency_checker.py     # Startup dependency verification & install
    device_probe.py           # Hardware detection (CPU/RAM/GPU/CUDA)
    diarization.py            # Cloud-free local speaker diarization (pyannote)
    model_manager.py          # Whisper model download & cache
    sdk_installer.py          # On-demand provider SDK installer
    wheel_installer.py        # PyPI wheel downloader/extractor (frozen builds)
    settings.py               # Persistent settings (JSON-backed dataclass)
    transcoder.py             # ffmpeg WAV normalisation
    updater.py                # GitHub Releases self-update
    job.py                    # Job / TranscriptionResult data models
    ai_service.py             # AI translation & summarization (OpenAI/Anthropic/Azure/Gemini/Copilot)
    live_transcription.py     # Real-time microphone transcription
    plugin_manager.py         # Plugin discovery, loading & lifecycle
    copilot_service.py        # GitHub Copilot SDK integration & agent management
    context_manager.py        # Context window management & token budgeting
    document_reader.py        # Document text extraction (DOCX/PDF/XLSX/RTF/TXT)
  providers/                    # 17 provider adapters (strategy pattern)
    base.py                   # TranscriptionProvider ABC + ProviderCapabilities
    local_whisper.py          # faster-whisper (local, free)
    openai_whisper.py         # OpenAI Whisper API
    google_speech.py          # Google Cloud Speech-to-Text
    gemini_provider.py        # Google Gemini
    azure_speech.py           # Microsoft Azure Speech Services
    azure_embedded.py         # Microsoft Azure Embedded Speech (offline)
    aws_transcribe.py         # Amazon Transcribe
    deepgram_provider.py      # Deepgram Nova-2
    assemblyai_provider.py    # AssemblyAI
    groq_whisper.py           # Groq LPU Whisper
    rev_ai_provider.py        # Rev.ai
    speechmatics_provider.py  # Speechmatics
    elevenlabs_provider.py    # ElevenLabs Scribe
    windows_speech.py         # Windows SAPI5 + WinRT (offline)
    vosk_provider.py          # Vosk offline speech (Kaldi-based)
    parakeet_provider.py      # NVIDIA Parakeet (NeMo ASR, English)
    auphonic_provider.py      # Auphonic audio post-production + transcription
  export/                       # Output formatters
    base.py                   # ExportFormatter ABC
    plain_text.py, markdown.py, html_export.py
    word_export.py, srt.py, vtt.py, json_export.py
  storage/
    database.py               # SQLite (WAL mode) for job metadata
    key_store.py              # keyring-backed credential store
  ui/
    main_frame.py             # Menu bar, splitter, status bar, tray integration
    queue_panel.py            # File queue list
    transcript_panel.py       # Transcript viewer / editor with speaker management
    settings_dialog.py        # Tabbed settings (9 tabs)
    progress_dialog.py        # Batch progress display
    model_manager_dialog.py   # Model download & management
    add_provider_dialog.py    # Cloud provider onboarding wizard
    setup_wizard.py           # First-run setup wizard (8 pages)
    tray_icon.py              # System tray (TaskBarIcon)
    live_transcription_dialog.py  # Live microphone transcription dialog
    ai_settings_dialog.py     # AI provider configuration dialog (5 providers)
    copilot_setup_dialog.py   # Copilot CLI installation & auth wizard
    copilot_chat_panel.py     # Interactive AI transcript chat panel
    agent_builder_dialog.py   # AI Action Builder — post-transcription template editor
    audio_player_dialog.py   # Audio preview dialog with clip selection
  utils/
    accessibility.py          # a11y helpers (announce, set_name, safe_call_after)
    constants.py              # App constants, model registry, path definitions
    platform_utils.py         # Cross-platform helpers (file open, disk space, CPU/GPU detection)
```

### Threading Model

- **Main thread**: wxPython event loop and all UI operations.
- **Worker threads**: `TranscriptionService` spawns N daemon threads (default 2)
  that process jobs from a `queue.Queue`.
- **Thread safety**: All UI updates go through `wx.CallAfter()` via
  `safe_call_after()`. The service uses a `threading.Lock` for shared state.
- **Update checker**: Runs in a separate daemon thread (startup + manual).

### Shutdown & Temp File Cleanup

BITS Whisperer implements a robust ordered shutdown sequence to prevent resource
leaks and orphaned temporary files:

1. **Ordered shutdown** (`MainFrame._on_close`): 5-step sequence — (1) stop
   transcription service, (2) stop Copilot service, (3) save settings, (4)
   cleanup tray icon, (5) remove stale temp files.
1. **Worker thread joining**: `TranscriptionService.stop()` joins worker threads
   with a 5-second timeout instead of fire-and-forget sentinel values.
1. **Per-job temp file tracking**: `TranscriptionService` tracks all temp files
   created by the preprocessor and transcoder during each job and cleans them up
   on job completion and on service shutdown.
1. **Identifiable temp file prefixes**: Transcoder uses `bw_transcode_*`,
   preprocessor uses `bw_preprocess_*`, and the updater uses `bw_update_*`
   prefixes to enable targeted cleanup.
1. **Stale temp file cleanup**: `MainFrame._cleanup_stale_temp_files()` scans
   the system temp directory on shutdown for files/directories older than 1 hour
   matching `bw_transcode_*`, `bw_preprocess_*`, or `bw_update_*` prefixes.
1. **Safety nets**: `App.OnExit()` and an `atexit` handler in `__main__.py`
   provide last-resort temp file cleanup if the normal shutdown path is
   bypassed.
1. **Secure temp file creation**: Transcoder uses `tempfile.mkstemp()` instead
   of the deprecated `tempfile.mktemp()` to avoid race conditions.

______________________________________________________________________

## 13. Data Model

### Job (`core/job.py`)

```text
Job
  - id: str (UUID)
  - file_path, file_name, file_size_bytes
  - duration_seconds: float
  - status: JobStatus (PENDING to TRANSCODING to TRANSCRIBING to COMPLETED | FAILED | CANCELLED)
  - provider, model, language
  - created_at, started_at, completed_at: ISO timestamps
  - progress_percent: 0-100
  - cost_estimate, cost_actual: float (USD)
  - transcript_path: str
  - error_message: str
  - include_timestamps, include_diarization: bool
  - clip_start_seconds, clip_end_seconds: float | None (optional clip range)
  - custom_name: str (user-defined display name)
  - ai_action_template: str (built-in preset name or AgentConfig JSON path)
  - ai_action_result: str (AI processing output)
  - ai_action_status: str ("" | "running" | "completed" | "failed")
  - ai_action_error: str (error message if AI action failed)
  - ai_action_attachments: list[dict] (per-job attachment overrides)
  - result: TranscriptionResult | None
```

### TranscriptionResult

```text
TranscriptionResult
  - job_id, audio_file, provider, model, language
  - duration_seconds
  - segments: list[TranscriptSegment]
      - start, end: float (seconds)
      - text: str
      - confidence: float (0-1)
      - speaker: str
  - full_text: str
  - speaker_map: dict[str, str]  # internal ID -> display name
  - created_at: str
```

### Persistence

| Store          | Backend                     | Contents                            |
| -------------- | --------------------------- | ----------------------------------- |
| Job metadata   | SQLite (WAL mode)           | Job history, status, paths          |
| API keys       | keyring (Credential Mgr)    | Provider API keys (20 entries)      |
| Recent files   | JSON file                   | Last 10 opened file paths           |
| Whisper models | File system (models dir)    | Downloaded faster-whisper models    |
| Provider SDKs  | File system (site-packages) | On-demand installed Python packages |
| Transcripts    | File system (transcripts)   | Default export location             |
| App log        | File system                 | Rotating log at `DATA_DIR/app.log`  |

______________________________________________________________________

## 14. Privacy & Security

- **Local by default**: Transcripts stored in user data directory (Windows:
  `%LOCALAPPDATA%/BITS Whisperer/`, macOS:
  `~/Library/Application Support/BITS Whisperer/`).
- **API keys**: Stored in OS credential vault (Windows Credential Manager /
  macOS Keychain) via `keyring` — never logged, printed, or committed.
- **Key validation**: Dry-run API call on save to verify keys are working.
- **No telemetry**: The app sends no usage data. Update checks are opt-in REST
  calls to the GitHub Releases API.
- **Offline-capable**: 5 local providers (Local Whisper, Windows SAPI5/WinRT,
  Azure Embedded Speech, Vosk, Parakeet) work without any internet connection.

______________________________________________________________________

## 15. Accessibility Requirements (Non-Negotiable)

Adapted from WCAG 2.1/2.2 for desktop; detailed rules in
`.github/accessibility.agent.md`.

| #   | Requirement                            | Implementation                                         |
| --- | -------------------------------------- | ------------------------------------------------------ |
| 1   | Every control has an accessible name   | `SetName()` on all widgets                             |
| 2   | Label association for all inputs       | `wx.StaticText` + `SetName()` pairing                  |
| 3   | Full keyboard reachability             | Tab order, mnemonics, accelerators                     |
| 4   | All actions available from menu bar    | Mnemonics (&) + accelerator keys                       |
| 5   | Progress reporting for screen readers  | `wx.Gauge` + status bar text updates                   |
| 6   | Cross-thread UI safety                 | `wx.CallAfter()` / `safe_call_after()`                 |
| 7   | High contrast support                  | `wx.SystemSettings.GetColour()`, no hard-coded colours |
| 8   | Screen reader compatibility            | Tested with NVDA keyboard-only                         |
| 9   | Focus management on dialog open/close  | Focus set to first interactive control                 |
| 10  | Status announcements for state changes | `announce_status()` helper                             |
| 11  | Consistent navigation patterns         | Splitter, Tab, List, Action pattern                    |

______________________________________________________________________

## 16. Keyboard Shortcuts

| Action                     | Shortcut       | Context    |
| -------------------------- | -------------- | ---------- |
| Add Files                  | Ctrl+O         | Global     |
| Add Folder                 | Ctrl+Shift+O   | Global     |
| Export Transcript          | Ctrl+E         | Global     |
| Find Next                  | F3             | Transcript |
| Start Transcription        | F5             | Global     |
| Pause / Resume             | F6             | Global     |
| Cancel Selected            | Delete         | Queue      |
| Clear Queue                | Ctrl+Shift+Del | Queue      |
| Settings                   | Ctrl+,         | Global     |
| Manage Models              | Ctrl+M         | Global     |
| Toggle Advanced Mode       | Ctrl+Shift+A   | Global     |
| Audio Preview              | Ctrl+Shift+P   | Global     |
| Preview Selected (Queue)   | Ctrl+Alt+P     | Queue      |
| Copilot Chat               | Ctrl+Shift+C   | Global     |
| About                      | F1             | Global     |
| Exit (or minimize to tray) | Alt+F4         | Global     |

______________________________________________________________________

## 17. Paths & Directories

All user data is stored under `%LOCALAPPDATA%/BITS Whisperer/BITSWhisperer/`
(via `platformdirs.user_data_dir`):

| Path                | Purpose                            |
| ------------------- | ---------------------------------- |
| `<DATA_DIR>/`       | Application data root              |
| `transcripts/`      | Default transcript export location |
| `models/`           | Downloaded Whisper model files     |
| `site-packages/`    | On-demand installed provider SDKs  |
| `bits_whisperer.db` | SQLite job database                |
| `app.log`           | Application log file               |
| `recent_files.json` | Recent file history                |

______________________________________________________________________

## 18. Dependencies

From `pyproject.toml`:

| Package                                 | Purpose                      |
| --------------------------------------- | ---------------------------- |
| wxPython ≥ 4.2.0                        | Desktop UI framework         |
| faster-whisper ≥ 1.0.0                  | Local Whisper inference      |
| openai ≥ 1.0.0                          | OpenAI Whisper API           |
| google-cloud-speech ≥ 2.20.0            | Google Speech-to-Text        |
| azure-cognitiveservices-speech ≥ 1.32.0 | Azure Speech Services        |
| deepgram-sdk ≥ 3.0.0                    | Deepgram Nova-2              |
| assemblyai ≥ 0.20.0                     | AssemblyAI                   |
| boto3 ≥ 1.28.0                          | Amazon Transcribe (AWS)      |
| google-genai ≥ 0.4.0                    | Google Gemini                |
| groq ≥ 0.4.0                            | Groq LPU Whisper             |
| rev-ai ≥ 2.17.0                         | Rev.ai                       |
| speechmatics-python ≥ 1.0.0             | Speechmatics                 |
| keyring ≥ 24.0.0                        | OS credential store          |
| python-docx ≥ 1.0.0                     | Word export                  |
| markdown ≥ 3.5                          | Markdown rendering           |
| Jinja2 ≥ 3.1.0                          | HTML template export         |
| pydub ≥ 0.25.1                          | Audio duration detection     |
| psutil ≥ 5.9.0                          | System resource monitoring   |
| platformdirs ≥ 4.0.0                    | Cross-platform data dirs     |
| httpx ≥ 0.25.0                          | HTTP client (update checker) |
| packaging ≥ 23.0                        | Version comparison           |
| sounddevice ≥ 0.4.6                     | Audio preview playback       |
| winsdk ≥ 1.0.0b10                       | Windows Speech Runtime (Win) |
| comtypes ≥ 1.2.0                        | COM interop (Win)            |

Dev dependencies: pytest, pytest-cov, black, ruff, mypy.

______________________________________________________________________

## 19. Implementation Status

- [x] Core transcription pipeline (preprocess, transcode, transcribe)
- [x] 17 transcription provider adapters (including Auphonic, Vosk, Parakeet)
- [x] 14 Whisper model definitions with hardware eligibility
- [x] 7-filter audio preprocessing with ffmpeg
- [x] 7 export format adapters
- [x] WXPython main frame with splitter layout
- [x] Queue panel with file list
- [x] Transcript panel with viewer/editor and speaker management
- [x] Settings dialog (7 tabs, Basic/Advanced visibility)
- [x] Model Manager dialog with download & eligibility
- [x] Hardware detection (CPU, RAM, GPU, CUDA)
- [x] API key storage via keyring
- [x] Cloud provider onboarding (Add Provider wizard with live validation)
- [x] Provider-specific settings (per-provider configuration during onboarding)
- [x] Speaker diarization (10 cloud providers + cloud-free pyannote.audio)
- [x] Speaker editing UI (rename, reassign, create speakers post-transcription)
- [x] Full Auphonic API integration (all audio algorithms, speech services,
  output formats)
- [x] SQLite database for job metadata
- [x] Batch processing with concurrent workers
- [x] Progress reporting (gauge + status bar + screen reader)
- [x] System tray icon with progress tooltip
- [x] Balloon notifications (job complete, batch complete, errors)
- [x] Minimize to tray / background processing
- [x] Auto-export on completion
- [x] Recent files menu (persistent, max 10)
- [x] Self-update via GitHub Releases (startup + manual)
- [x] Basic/Advanced mode toggle with persistent experience_mode setting
- [x] View Log (opens app.log)
- [x] Full accessibility (names, labels, keyboard, screen reader)
- [x] First-run setup wizard (8-page guided experience with mode selection and
  AI/Copilot setup)
- [x] Cross-platform support (Windows 10+ and macOS 12+)
- [x] Disk space pre-checks before model downloads
- [x] Comprehensive user guide (docs/USER_GUIDE.md)
- [x] Automatic ffmpeg dependency installation (winget on Windows, manual
  instructions fallback)
- [x] Persistent application settings (JSON-backed dataclass)
- [x] On-demand provider SDK installer (WheelInstaller + sdk_installer)
- [x] Pre-transcription SDK checks (ensure_sdk before job dispatch)
- [x] Lightweight PyInstaller packaging (~40 MB with lean build)
- [x] Inno Setup Windows installer script
- [x] Queue panel context menu with wired handlers
- [x] Find Next (F3) in transcript search
- [x] Setup Wizard accessible from Help menu
- [x] Learn more about BITS link in Help menu
- [x] Add Provider menu item in Tools menu
- [x] Provider activation tracking (activated_providers in settings)
- [x] AI translation & summarization (5 providers: OpenAI, Anthropic, Azure
  OpenAI, Gemini, Copilot)
- [x] Google Gemini AI provider (translation, summarization)
- [x] GitHub Copilot SDK integration (CopilotService, async client, streaming,
  custom tools)
- [x] Interactive AI Chat Panel (Ctrl+Shift+C, streaming, quick actions,
  transcript context)
- [x] Copilot Setup Wizard (4-step: CLI install, SDK install, auth, test)
- [x] Agent Builder dialog (4-tab: Identity, Instructions with presets, Tools,
  Welcome Message)
- [x] CopilotSettings dataclass (11 fields) in AppSettings
- [x] Installer Copilot CLI install task (WinGet optional)
- [x] 191 tests with full coverage for Gemini and Copilot features
- [x] AI model catalog with real-time pricing (22 models across 4 providers)
- [x] Copilot subscription tier-based model selection
  (Free/Pro/Business/Enterprise)
- [x] Google Gemma models (5 variants: 27B, 12B, 4B, 1B, 3n-E4B via Gemini API)
- [x] Custom vocabulary for AI translation/summarization accuracy
- [x] 10 built-in prompt templates (4 translation, 4 summarization, 2 analysis)
- [x] Multi-language simultaneous translation
- [x] Real-time streaming from cloud providers (Deepgram, AssemblyAI)
- [x] 255 tests with full coverage for all Phase 4 features
- [x] TreeView queue panel with folder grouping and collapsible nodes
- [x] Folder transcription with cost estimation and confirmation dialog
- [x] Conditional Chat tab visibility based on AI provider configuration
- [x] Queue panel toolbar with filter/search, Clear Completed, Retry All Failed
- [x] Budget limits per provider and per model with confirmation dialogs
- [x] Setup Wizard budget configuration page (9 pages total)
- [x] Custom job naming (F2 rename, context menu, AddFileWizard)
- [x] Job properties dialog (file details, status, cost, timestamps)
- [x] Queue context menus (file: Rename/Retry/Cancel/Remove/Properties; folder:
  Rename/Remove/Expand)
- [x] Batch operations (Clear Completed, Retry All Failed, Retry Selected)
- [x] Real-time queue filter/search bar
- [x] Ollama local AI provider (local LLM inference via OpenAI-compatible API)
- [x] AI Actions — automatic post-transcription AI processing
- [x] 6 built-in AI Action presets (Meeting Minutes, Action Items, Executive
  Summary, Interview Notes, Lecture Notes, Q&A Extraction)
- [x] AI Action Builder dialog (8 presets, 4-tab template editor)
- [x] AI Action selection in AddFileWizard
- [x] AI Action result display in Transcript Panel
- [x] AI Action status indicators in Queue Panel (⭐/⏳/✓/✗)
- [x] 501 tests with full coverage for all features
- [x] Slash command system (28 commands, autocomplete, 2 categories)
- [x] Context window management (model-aware token budgeting, 4 strategies,
  conversation trimming)
- [x] 674 tests with full coverage for all features
- [x] Robust shutdown procedures (ordered shutdown, worker thread joining, temp
  file cleanup, safety nets)
- [x] Document attachments for AI Actions (attach reference documents — DOCX,
  PDF, XLSX, RTF, TXT — to provide additional context for AI processing)
- [x] Audio preview with pitch-preserving speed control and clip selection

______________________________________________________________________

## 20. Success Metrics

| Metric                        | Target                     |
| ----------------------------- | -------------------------- |
| Time to first transcription   | < 2 minutes from install   |
| Keyboard-only task completion | 100% of features           |
| Screen reader compatibility   | NVDA pass on all workflows |
| Provider switch time          | < 30 seconds               |
| Batch throughput (local)      | Limited only by hardware   |
| Cold start time               | < 5 seconds                |

______________________________________________________________________

## 21. Decisions Log

| Decision                             | Reasoning                                                                        |
| ------------------------------------ | -------------------------------------------------------------------------------- |
| WXPython over Electron/Qt            | Best native accessibility (MSAA/UIA) on Windows                                  |
| faster-whisper over openai-whisper   | CTranslate2 -- 4x faster, lower memory, same accuracy                            |
| Menu bar as primary interface        | Screen reader–friendly; discoverable via mnemonics                               |
| keyring for API keys                 | OS credential store > env vars or config files                                   |
| Simple/Advanced mode toggle          | Consumer-friendly defaults; power users opt in; mode persisted across sessions   |
| Basic mode provider filtering        | Only show activated cloud providers in Basic mode to reduce clutter              |
| Cloud provider onboarding            | Three-step wizard with live API validation before activation                     |
| Minimize to tray by default          | Long batch jobs shouldn't block the taskbar                                      |
| Balloon notifications                | Native Windows toast API via wx.adv; no extra deps                               |
| JSON for recent files                | Lightweight; no schema migration needed                                          |
| No auto-install for updates          | Security -- user controls what runs on their machine                             |
| On-demand SDK install                | Keeps installer ~40 MB; SDKs downloaded on first use from PyPI                   |
| WheelInstaller over pip              | Frozen apps have no Python interpreter; direct wheel extraction works everywhere |
| ffmpeg for preprocessing             | Ubiquitous; no native lib compilation needed                                     |
| pyannote.audio for local diarization | Best open-source speaker diarization; optional dependency                        |
| Provider configure() method          | Data-driven settings injection; no provider subclass modification needed         |
| SpeakerRenameDialog over inline      | Global rename is safer and clearer than per-line editing                         |
| speaker_map on TranscriptionResult   | Separates internal IDs from display names; lossless rename                       |
| Google Gemini for AI                 | Fast, affordable translation/summarization; multimodal capable                   |
| GitHub Copilot SDK over raw API      | CLI-based auth, streaming, tool calling, session management built-in             |
| Agent Builder as separate dialog     | Complex config deserves dedicated UI; presets simplify setup                     |
| CopilotSettings as nested dataclass  | Clean separation from AI settings; many Copilot-specific fields                  |
| TreeView for queue panel             | Hierarchical folder grouping; native accessibility; collapsible nodes            |
| Budget limits per provider+model     | Granular cost control without blocking free/local providers                      |
| AI Actions via existing AgentConfig  | Reuse existing template infrastructure; provider-agnostic design                 |
| Ollama via OpenAI-compatible API     | No new SDK needed; uses existing openai package for API calls                    |
| Built-in presets for AI Actions      | Common use cases work out of the box; no configuration required                  |
