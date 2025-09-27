#!/usr/bin/env python3
"""
Minimal Whoami Example for Malice Network Python SDK

This example demonstrates the simplest way to execute a whoami command
on a remote session using the Malice Network Python SDK.

Requirements:
- A running Malice Network server
- A valid client.auth file in the same directory
- At least one active session on the server

Usage:
    python whoami.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for IoM import
sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    """Execute whoami command on the first available session."""
    try:
        # Import SDK components
        from IoM import MaliceClient
        from IoM.proto.modulepb import Request

        # Load client configuration
        auth_file = Path("client.auth")
        if not auth_file.exists():
            print("❌ Error: client.auth file not found")
            print("Please ensure you have a valid client.auth file in the current directory")
            return 1

        # Connect to Malice Network server
        client = MaliceClient.from_config_file(auth_file)

        async with client:
            print("✅ Connected to Malice Network server")

            # Get available sessions
            await client.update_sessions()
            sessions = client.cached_sessions

            if not sessions:
                print("❌ No active sessions found")
                print("Please ensure there are active implants connected to the server")
                return 1

            print(f"📋 Found {len(sessions)} active sessions")

            # Use the first available session
            session_id = list(sessions.keys())[0]
            session_info = sessions[session_id]
            print(f"🎯 Using session: {session_info.name} ({session_id[:8]}...)")

            # Get session wrapper
            session = await client.sessions.get_session(session_id)

            # Execute whoami command
            print("🔍 Executing whoami command...")
            task = await session.whoami(Request(name="whoami"))
            print(f"📋 Task created with ID: {task.task_id}")

            # Wait for task completion
            print("⏳ Waiting for task completion...")
            task_context = await client.wait_task_finish(task)

            # Display result
            if task_context.spite and task_context.spite.response:
                result = task_context.spite.response.output
                print(f"🎯 Whoami result: {result}")
            else:
                print("⚠️  Task completed but no output received")

        print("✅ Whoami command completed successfully!")
        return 0

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Please ensure the IoM package is installed: pip install -e .")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)