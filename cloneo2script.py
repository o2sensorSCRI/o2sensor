import os
import shutil
import subprocess
import tempfile

# Paths and repo
target_dir = "/chronic/O2_Sensor"
repo_url = "https://github.com/o2sensorSCRI/o2sensor.git"

def cleanup_temp_dir(path):
    """Deletes the temporary folder used for cloning."""
    if os.path.exists(path):
        shutil.rmtree(path)
        print(f"🗑️ Deleted temporary folder: {path}")

def main():
    # Create a named temporary directory
    tmp_dir = tempfile.mkdtemp(prefix="o2sensor_clone_")
    print(f"📁 Cloning into temporary folder: {tmp_dir}")

    try:
        subprocess.run(["git", "clone", "--depth", "1", repo_url, tmp_dir], check=True)

        # Copy files to target, overwriting existing ones
        for root, dirs, files in os.walk(tmp_dir):
            rel_path = os.path.relpath(root, tmp_dir)
            dest_dir = os.path.join(target_dir, rel_path)

            os.makedirs(dest_dir, exist_ok=True)

            for file in files:
                src_file = os.path.join(root, file)
                dest_file = os.path.join(dest_dir, file)

                shutil.copy2(src_file, dest_file)
                print(f"✔️ Copied: {src_file} → {dest_file}")

        print("✅ Repo files updated in /chronic/O2_Sensor.")

    finally:
        # Always clean up temp folder
        cleanup_temp_dir(tmp_dir)

if __name__ == "__main__":
    main()
