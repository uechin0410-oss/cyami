"""ターミナルで対話する問い合わせ対応エージェント。"""

from __future__ import annotations

import argparse

import anyio
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from .agent import build_options


async def chat(verbose: bool, model: str | None) -> None:
    async with ClaudeSDKClient(options=build_options(model=model)) as client:
        print("問い合わせ対応エージェントです。終了するには 'exit' と入力してください。\n")
        while True:
            try:
                user_input = input("お客様> ").strip()
            except EOFError:
                break
            if user_input.lower() in {"exit", "quit"}:
                break
            if not user_input:
                continue

            await client.query(user_input)
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            print(f"\nサポート> {block.text}\n")
                        elif isinstance(block, ToolUseBlock) and verbose:
                            print(f"  [tool] {block.name} {block.input}")
                elif isinstance(message, ResultMessage) and verbose:
                    cost = message.total_cost_usd or 0.0
                    print(f"  [result] turns={message.num_turns} cost=${cost:.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true", help="ツール呼び出しとコストを表示")
    parser.add_argument("--model", help="使用するモデル ID")
    args = parser.parse_args()
    anyio.run(chat, args.verbose, args.model)


if __name__ == "__main__":
    main()
