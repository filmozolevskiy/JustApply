import asyncio
import sys
import os
import google.generativeai as genai
from dotenv import load_dotenv

def main():
    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    # Handle model flag if passed via command line
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--prompt", help="Prompt to send to Gemini")
    parser.add_argument("-m", "--model", help="Model name")
    args = parser.parse_args()

    if args.model:
        model_name = args.model
    
    prompt = args.prompt
    if not prompt:
        # Try to read from stdin if no prompt flag
        if not sys.stdin.isatty():
            prompt = sys.stdin.read()
    
    if not prompt:
        print("Error: No prompt provided", file=sys.stderr)
        sys.exit(1)

    genai.configure(api_key=api_key, transport="rest")
    model = genai.GenerativeModel(model_name)

    try:
        response = model.generate_content(prompt)
        print(response.text)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
