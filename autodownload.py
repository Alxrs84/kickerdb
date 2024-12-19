import requests
import hashlib
import os
from datetime import datetime

# Konfiguration
url = "https://www.kicker-libero.de/api/sportsdata/v1/players-details/se-k00012024.csv"
download_dir = "/volume2/homes/Alex/Drive/PythonProjects/kickerdb/autodownload"
hash_file = os.path.join(download_dir, "last_hash.txt")

def download_file(url, temp_path):
    r = requests.get(url)
    if r.status_code == 200:
        with open(temp_path, 'wb') as f:
            f.write(r.content)
        return True
    return False

def file_hash(path):
    sha = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            sha.update(chunk)
    return sha.hexdigest()

def load_last_hash():
    if os.path.exists(hash_file):
        with open(hash_file, 'r') as f:
            return f.read().strip()
    return None

def save_hash(h):
    with open(hash_file, 'w') as f:
        f.write(h)

def main():
    temp_path = os.path.join(download_dir, "temp.csv")
    if download_file(url, temp_path):
        new_hash = file_hash(temp_path)
        old_hash = load_last_hash()

        if new_hash != old_hash:
            # Datei hat sich verändert
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            new_filename = f"data_{timestamp}.csv"
            new_filepath = os.path.join(download_dir, new_filename)
            os.rename(temp_path, new_filepath)
            save_hash(new_hash)
            print(f"Neue Version gespeichert als {new_filename}")
        else:
            # Keine Änderung, temporäre Datei löschen
            os.remove(temp_path)
            print("Keine Änderung festgestellt.")
    else:
        print("Download fehlgeschlagen")

if __name__ == "__main__":
    main()
