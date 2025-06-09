import os
import shutil
import subprocess
import tempfile

# Target directory where the repo contents should be copied
TARGET_DIR = os.path.expanduser("~/O2_Sensor")  # Update if needed
REPO_URL = "https://github.com/o2sensorSCRI/o2sensor.git"

def clone_repo(temp_dir):
    print(f"🔄 Cloning into: {temp_dir}")
    subprocess.run(["git", "clone", "--depth", "1", REPO_URL, temp_dir], check=True)

def copy_repo_contents(src_dir, dst_dir):
    print(f"📂 Copying files to: {dst_dir}")
    for root, dirs, files in os.walk(src_dir):
        rel_path = os.path.relpath(root, src_dir)
        dest_path = os.path.join(dst_dir, rel_path)

        os.makedirs(dest_path, exist_ok=True)

        for file in files:
            src_file = os.path.join(root, file)
            dst_file = os.path.join(dest_path, file)

            shutil.copy2(src_file, dst_file)
            print(f"✔️  Copied: {src_file} → {dst_file}")

def main():
    temp_dir = tempfile.mkdtemp(prefix="o2sensor_tmp_")

    try:
        os.makedirs(TARGET_DIR, exist_ok=True)
        clone_repo(temp_dir)
        copy_repo_contents(temp_dir, TARGET_DIR)
        print("✅ Update complete.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Git clone failed: {e}")
    except Exception as ex:
        print(f"❌ Unexpected error: {ex}")
    finally:
        shutil.rmtree(temp_dir)
        print(f"🧹 Deleted temp folder: {temp_dir}")

if __name__ == "__main__":
    main()
