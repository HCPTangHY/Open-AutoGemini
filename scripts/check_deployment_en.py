import argparse
import json
import os

import requests

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tool for checking if model deployment is successful",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage examples:
  python scripts/check_deployment_en.py --base-url http://localhost:8000/v1 --apikey your-key --model autoglm-phone-9b
  python scripts/check_deployment_en.py --base-url http://localhost:8000/v1 --apikey your-key --model autoglm-phone-9b --messages-file custom.json
        """,
    )

    parser.add_argument(
        "--base-url",
        type=str,
        required=True,
        help="Base URL of the API service, e.g.: http://localhost:8000/v1",
    )

    parser.add_argument(
        "--apikey", type=str, default="EMPTY", help="API key (default: EMPTY)"
    )

    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Name of the model to test, e.g.: autoglm-phone-9b",
    )

    parser.add_argument(
        "--messages-file",
        type=str,
        default="scripts/sample_messages_en.json",
        help="Path to JSON file containing test messages (default: scripts/sample_messages_en.json)",
    )

    parser.add_argument(
        "--max-tokens",
        type=int,
        default=3000,
        help="Maximum generation tokens (default: 3000)",
    )

    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature (default: 0.0)",
    )

    parser.add_argument(
        "--top_p",
        type=float,
        default=0.85,
        help="Nucleus sampling parameter (default: 0.85)",
    )

    parser.add_argument(
        "--frequency_penalty",
        type=float,
        default=0.2,
        help="Frequency penalty parameter (default: 0.2)",
    )

    args = parser.parse_args()

    # Read test messages
    if not os.path.exists(args.messages_file):
        print(f"Error: Message file {args.messages_file} does not exist")
        exit(1)

    with open(args.messages_file) as f:
        messages = json.load(f)

    base_url = args.base_url
    api_key = args.apikey
    model = args.model

    print(f"Starting model inference test...")
    print(f"Base URL: {base_url}")
    print(f"Model: {model}")
    print(f"Messages file: {args.messages_file}")
    print("=" * 80)

    try:
        url = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": args.max_tokens,
            "temperature": args.temperature,
            "top_p": args.top_p,
            "frequency_penalty": args.frequency_penalty,
            "stream": False,
        }

        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        print("\nModel inference result:")
        print("=" * 80)
        print(data["choices"][0]["message"]["content"])
        print("=" * 80)

        usage = data.get("usage")
        if usage:
            print(f"\nStatistics:")
            print(f"  - Prompt tokens: {usage.get('prompt_tokens')}")
            print(f"  - Completion tokens: {usage.get('completion_tokens')}")
            print(f"  - Total tokens: {usage.get('total_tokens')}")

        print(
            f"\nPlease evaluate the above inference result to determine if the model deployment meets expectations."
        )

    except Exception as e:
        print(f"\nError occurred while calling API:")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print(
            "\nTip: Please check if base_url, api_key and model parameters are correct, and if the service is running."
        )
        exit(1)
