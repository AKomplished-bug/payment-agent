#!/usr/bin/env python3
"""
Interactive CLI to run the payment agent.
Usage: python cli.py
"""
import os
import sys
from dotenv import load_dotenv


def main():
    load_dotenv()
    os.environ.setdefault("LOG_LEVEL", "WARNING")
    if not os.getenv("LLM_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        print("ERROR: Set LLM_API_KEY (or OPENAI_API_KEY) environment variable first.")
        print("  export LLM_API_KEY=sk-...")
        sys.exit(1)

    from agent import Agent
    agent = Agent()

    print("Payment Agent — type 'quit' or Ctrl+C to exit\n")
    print("-" * 50)

    # Send empty first message to trigger greeting
    resp = agent.next("Hi")
    print(f"Agent: {resp['message']}\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "bye"):
            print("Agent: Thank you. Goodbye!")
            break

        resp = agent.next(user_input)
        print(f"\nAgent: {resp['message']}\n")


if __name__ == "__main__":
    main()
