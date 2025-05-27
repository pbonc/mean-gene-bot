import os

# What your bot is currently doing:
old_path = os.path.join(os.path.dirname(__file__), "bot", "data", "sfx")
print("🔍 Old logic path:", old_path)

# What we told it to do:
new_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "sfx"))
print("✅ New absolute path:", new_path)

# Show contents of the folder
if os.path.exists(new_path):
    print("📂 Contents of SFX folder:", os.listdir(new_path))
else:
    print("❌ SFX folder not found.")
