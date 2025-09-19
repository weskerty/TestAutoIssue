import os
import json
from pathlib import Path

def get_files(directory, extensions):
    """Get all files in a directory with specific extensions."""
    try:
        return sorted([
            f for f in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, f)) and os.path.splitext(f)[1].lower() in extensions
        ])
    except Exception as e:
        print(f"Error reading directory {directory}: {e}")
        return []

def process_gallery(folder_path):
    """Process a single gallery folder inside web/Dinamico."""
    if not os.path.exists(folder_path):
        print(f"Directory not found: {folder_path}")
        return []
    
    image_files = get_files(folder_path, {'.jpg', '.jpeg', '.png', '.gif', '.webp'})
    html_files = get_files(folder_path, {'.html', '.md'})
    gallery_items = []
    
    html_file_map = {os.path.splitext(f)[0]: f for f in html_files}
    
    for image_file in image_files:
        name = os.path.splitext(image_file)[0]
        html_file = html_file_map.get(name)
        
        if html_file:
            gallery_items.append({
                "image": f"web/Dinamico/{os.path.basename(folder_path)}/{image_file}",
                "link": f"web/Dinamico/{os.path.basename(folder_path)}/{html_file}",
                "name": name
            })
    
    return gallery_items

def create_gallery_json():
    """Create the main gallery JSON file scanning all subfolders in web/Dinamico."""
    base_path = Path("web", "Dinamico")
    galleries = {}
    
    if not base_path.exists():
        print(f"Base directory not found: {base_path}")
        return
    
    for folder in base_path.iterdir():
        if folder.is_dir():
            print(f"Processing folder: {folder.name}")
            galleries[folder.name] = {
                "images": process_gallery(folder)
            }
    
    try:
        with open(base_path / 'data.json', 'w', encoding='utf-8') as f:
            json.dump({"galleries": galleries}, f, indent=2, ensure_ascii=False)
        print("JSON file created successfully")
    except Exception as e:
        print(f"Error creating JSON file: {e}")

if __name__ == "__main__":
    create_gallery_json()
