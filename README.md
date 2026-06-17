# Free Frontier Proxy

This project provides a robust, resilient proxy that enables free access to frontier-class AI models. 

Built on top of [LiteLLM Proxy](https://github.com/BerriAI/litellm), this repository is specifically configured to leverage high-quality free API tiers. By combining providers such as Google AI Studio, Groq, NVIDIA NIM, and OpenRouter, the proxy creates a highly available and unified OpenAI-compatible endpoint. If a primary free tier encounters a rate limit, the proxy automatically falls back to the next available provider. This ensures your applications remain operational without incurring inference costs.

## Core Architecture and Value Proposition

API costs can scale rapidly in AI application development. This proxy mitigates those costs by acting as an intelligent load balancer across established free APIs:

- **Frontier Models:** Access models including `gemini-flash` (Gemini 3 Flash), `groq-maverick` (Llama 4 Maverick), and `nvidia-kimi` (Kimi K2.6) at no cost using Google AI Studio, Groq, and NVIDIA NIM.
- **Graceful Fallbacks:** When a primary API key reaches its rate limit (429 error), the proxy automatically cascades the request through a prioritized list of alternatives. For example, a failed request to Gemini Flash will fallback to Groq Maverick, NVIDIA Kimi, Groq Qwen, and eventually to OpenRouter free models and local CPU backups.
- **High-Performance Open Source:** Utilizes Groq's LPU for ultra-low-latency inference on Llama 4 Maverick and Qwen3-32B, plus NVIDIA NIM for Kimi K2.6 and DeepSeek V4 Pro.
- **Ultimate Reliability:** Incorporates OpenRouter's completely subsidized free endpoints (`:free` suffix) and local CPU-bound models (via `ollama`) as a final safeguard to ensure a response is always generated.

## Prerequisites

- [Python 3.12+](https://www.python.org/)
- [uv](https://github.com/astral-sh/uv) (recommended for dependency management)

## Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/robpodosek/free-frontier-proxy.git
   cd free-frontier-proxy
   ```

2. **Configure Environment Variables:**
   Copy the example environment file and add your API keys:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and configure your keys. You do not need to populate all keys to start, but configuring multiple providers increases the resilience of the proxy.
   - [Google AI Studio](https://aistudio.google.com/app/apikey) (Gemini 3 Flash, Gemini 3.1 Flash-Lite)
   - [Groq](https://console.groq.com/keys) (Llama 4 Maverick, Qwen3-32B)
   - [NVIDIA NIM](https://build.nvidia.com/) (Kimi K2.6, DeepSeek V4 Pro)
   - [OpenRouter](https://openrouter.ai/keys) (Qwen3 Coder, DeepSeek V4 Flash, Gemma 4 — all `:free`)

3. **Install Dependencies:**
   Dependencies are managed by `uv` and will be installed automatically the first time the script is executed.

## Usage

### Local Development
For development and local testing, run the script directly. This provides instant logs and allows you to test code changes immediately.

```bash
uv run main.py
```

### Production Deployment (Docker)
For hosting on a VPS, the recommended approach is Docker. This ensures the proxy runs silently in the background and automatically restarts on server reboots.

1. Ensure your API keys are available. If you use a tool like `direnv` instead of a `.env` file, the `docker-compose.yml` is configured to inherit keys from your host shell automatically.
2. Build and start the container in detached mode:
   ```bash
   docker compose up -d --build
   ```
3. To view real-time logs:
   ```bash
   docker compose logs -f
   ```
4. To stop the container:
   ```bash
   docker compose down
   ```

The proxy will initialize and listen on `http://localhost:4000`.

### Example API Call

The proxy functions as a drop-in replacement for any OpenAI-compatible client. Configure your client's base URL to `http://localhost:4000/v1`.

```bash
curl --request POST \
  --url http://localhost:4000/v1/chat/completions \
  --header 'Content-Type: application/json' \
  --data '{
    "model": "gemini-flash",
    "messages": [
      {
        "role": "user",
        "content": "Provide a brief summary of how this proxy functions."
      }
    ]
  }'
```

## Configuration

The routing logic and fallback cascades are defined in `config.yaml`. You can edit this file to add new models, change providers, or adjust the fallback priorities to suit your requirements.

## Zero-Cost Safeguards

To achieve the primary goal of zero-cost frontier model usage without any risk of accidental billing, the proxy uses specific safeguards for its providers:

### 1. Google AI Studio (Gemini) Safeguard
> [!IMPORTANT]
> **Google AI Studio projects with no billing account linked will never charge you.**
> - If you use a standard Google AI Studio developer API key *without* linking a Google Cloud Platform (GCP) billing account, you are fully secured under their generous Free Tier limits.
> - When these rate limits are reached, Google AI Studio does **not** charge you; instead, it returns a standard `429 Resource Exhausted` error. The proxy automatically catches this error and transparently redirects your request to alternative free providers in the fallback list (such as Groq or NVIDIA NIM).
> - **Note:** As of April 2026, Gemini Pro models are no longer available on the free tier. Only Flash and Flash-Lite models are included. This proxy is configured accordingly.
> - **Caution:** If you have manually linked a GCP billing account to the specific project containing your API key, Google will charge you for usage. To ensure zero cost, use a dedicated Google AI Studio project with **no billing active**.

### 2. OpenRouter Safeties
> [!TIP]
> **Enforced Subsidized Routing via `:free` Suffix**
> - OpenRouter model configurations in `config.yaml` explicitly append the `:free` suffix to model names (e.g., `qwen/qwen3-coder:free`).
> - This guarantees that OpenRouter will only route requests through completely subsidized, free channels.
> - Even if you have credit card details or a positive balance configured on your OpenRouter account, appending `:free` ensures that OpenRouter will never deduct funds for these requests.

### 3. Additional Providers
- **Groq:** Free developer tier with rate limits (~30 RPM, ~1000 RPD). No charges unless a paid plan is explicitly and manually subscribed to.
- **NVIDIA NIM:** Free prototyping endpoints (~40 RPM). Rate-limited but never charges for the hosted API catalog. Production use requires a separate NVIDIA AI Enterprise license.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
