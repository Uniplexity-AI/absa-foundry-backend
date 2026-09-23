# Local LLM Offline Weights (Next Best Action & Decision Intelligence)

This directory is the designated location for local LLM weights running in-process via `llama-cpp-python` (CPU-optimized, no external daemon or open ports).

## Expected Model File
* **Filename**: `qwen2.5-7b-instruct.gguf`
* **Path**: `customer-lifecycle-ai/models/llm/qwen2.5-7b-instruct.gguf`
* **Size**: ~4.68 GB (Q4_K_M quantization)
* **Model**: Qwen 2.5 7B Instruct

> ⚠️ **Note**: Because this model is ~4.7 GB, it is excluded from Git (`.gitignore`). It must be placed on the target machine out-of-band (e.g. via internal network share, USB, or artifact repository).

## Target Machine Setup Instructions

1. **Place the Model Weights**:
   Copy `qwen2.5-7b-instruct.gguf` into this directory:
   ```powershell
   # If copying from another directory or drive:
   Copy-Item "D:\shared\qwen2.5-7b-instruct.gguf" -Destination ".\models\llm\qwen2.5-7b-instruct.gguf"
   ```

2. **Custom Location via `.env` (Optional)**:
   If the model is stored on a shared drive or central directory, specify its absolute path in `.env`:
   ```bash
   NBA_MODEL_PATH=C:\Shared\models\qwen2.5-7b-instruct.gguf
   ```

3. **Install `llama-cpp-python` Prebuilt CPU Wheel**:
   On Windows without Visual Studio C++ build tools, install the prebuilt wheel:
   ```powershell
   pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
   ```
   *(Or install from an offline wheel file in corporate air-gapped environments).*
