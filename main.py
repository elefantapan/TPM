import sys
import os
import shutil
import struct
import json

import sys, os, struct, json

import customtkinter as ctk
from tkinter import messagebox

SIGS = {
    b'\x89PNG\r\n\x1a\n': '.png',
    b'\xFF\xD8\xFF': '.jpg',
    b'OggS': '.ogg',
    b'RIFF': '.wav',  # RIFF could be many formats; we'll write .wav by default
    b'PK\x03\x04': '.zip',
}

GLSL_MAGIC = b'\xE8\x01\x00\x00\x00\x00\x00\x00'

def guess_ext(byts):
    for sig, ext in SIGS.items():
        if byts.startswith(sig):
            return ext
    if byts[:4].isdigit() and b'JFIF' in byts[:64]:
        return '.jpg'
    return '.bin'


def extract_length_prefixed(path, outdir):
    records = []
    with open(path, 'rb') as f:
        idx = 0
        pos = 0
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            length = struct.unpack('<I', hdr[:4])[0]
            reserved = hdr[4:8]
            data = f.read(length)
            if len(data) != length:
                break
            ext = guess_ext(data[:16])
            name = f"{idx:04d}_len_{length}{ext}"
            outpath = os.path.join(outdir, name)
            with open(outpath, 'wb') as out:
                out.write(data)
            records.append({
                'index': idx,
                'offset': pos,
                'length': length,
                'reserved': list(reserved),
                'filename': name
            })
            pos += 8 + length
            idx += 1
    return records


def extract_by_signature(path, outdir):
    data = open(path, 'rb').read()
    found = []
    i = 0
    idx = 0
    while i < len(data):
        nextpos = None
        nextsig = None
        for sig in SIGS:
            p = data.find(sig, i)
            if p != -1 and (nextpos is None or p < nextpos):
                nextpos = p
                nextsig = sig
        if nextpos is None:
            break
        start = nextpos
        ext = SIGS[nextsig]
        if nextsig == b'\x89PNG\r\n\x1a\n':
            pos = start + 8
            while True:
                if pos + 8 > len(data):
                    break
                clen = struct.unpack('>I', data[pos:pos+4])[0]
                ctype = data[pos+4:pos+8]
                pos = pos + 8 + clen + 4
                if ctype == b'IEND' or pos > len(data):
                    break
            end = pos
        elif nextsig == b'\xFF\xD8\xFF':
            end = data.find(b'\xFF\xD9', start)
            if end == -1:
                end = len(data)
            else:
                end += 2
        elif nextsig == b'OggS':
            nxt = data.find(b'OggS', start + 4)
            end = nxt if nxt != -1 else len(data)
        elif nextsig == b'RIFF':
            if start + 8 <= len(data):
                sz = struct.unpack('<I', data[start+4:start+8])[0]
                end = start + 8 + sz
                if end > len(data):
                    end = len(data)
            else:
                end = len(data)
        else:
            end = len(data)
        blob = data[start:end]
        name = f"{idx:04d}_sig{ext}"
        outpath = os.path.join(outdir, name)
        with open(outpath, 'wb') as out:
            out.write(blob)
        found.append({
            'index': idx,
            'start': start,
            'end': end,
            'length': end - start,
            'filename': name
        })
        idx += 1
        i = end
    return found


def check_for_glsl(path, outdir):
    """If file starts with GLSL_MAGIC, extract the rest as UTF-8 text."""
    with open(path, 'rb') as f:
        header = f.read(8)
        if header != GLSL_MAGIC:
            return False
        rest = f.read()
    try:
        text = rest.decode('utf-8', errors='replace')
    except Exception:
        text = rest.decode('latin-1', errors='replace')

    glsl_path = os.path.join(outdir, 'shader_extracted.glsl')
    with open(glsl_path, 'w', encoding='utf-8') as g:
        g.write(text)
    print(f"GLSL data detected — extracted to {glsl_path}")
    return True


def run(path):
    base = os.path.basename(path)
    outdir = os.path.join('assets/extracted', base)
    os.makedirs(outdir, exist_ok=True)

    # Check for GLSL special header
    if check_for_glsl(path, outdir):
        meta = {'method': 'glsl_detected', 'records': [{'filename': 'shader_extracted.glsl'}]}
    else:
        print("Trying length-prefixed extraction...")
        recs = extract_length_prefixed(path, outdir)
        if recs:
            print(f"Extracted {len(recs)} records using length-prefixed method.")
            meta = {'method': 'length_prefixed', 'records': recs}
        else:
            print("No length-prefixed records found — falling back to signature scanning...")
            recs2 = extract_by_signature(path, outdir)
            print(f"Extracted {len(recs2)} files using signature scanning.")
            meta = {'method': 'signature_scan', 'records': recs2}

    with open(os.path.join(outdir, 'index.json'), 'w', encoding='utf-8') as jf:
        json.dump(meta, jf, indent=2)
    print("Done. See", outdir)


def rebuild_from_extracted(out_path, extracted_dir, replace_map=None, keep_reserved=True):
    """
    Rebuilds a .data file from extracted blobs using index.json.
    """
    idxfile = os.path.join(extracted_dir, 'index.json')
    if not os.path.exists(idxfile):
        raise FileNotFoundError("index.json not found in extracted dir: " + idxfile)
    meta = json.load(open(idxfile, 'r', encoding='utf-8'))
    records = meta['records']
    with open(out_path, 'wb') as out:
        for rec in records:
            index = rec.get('index') if 'index' in rec else rec.get('idx')
            # determine input blob path
            orig_file = os.path.join(extracted_dir, rec['filename'])
            if replace_map and index in replace_map:
                blob_path = replace_map[index]
                if not os.path.exists(blob_path):
                    raise FileNotFoundError("Replacement blob not found: "+blob_path)
            else:
                blob_path = orig_file
                if not os.path.exists(blob_path):
                    raise FileNotFoundError("Expected blob not found: "+blob_path)
            data = open(blob_path, 'rb').read()
            length = len(data)
            out.write(struct.pack('<I', length))
            if keep_reserved and 'reserved' in rec:
                res = bytes(rec['reserved'])
                if len(res) != 4:
                    res = (res + b'\x00\x00\x00\x00')[:4]
                out.write(res)
            else:
                out.write(b'\x00\x00\x00\x00')
            out.write(data)
    print("Wrote", out_path)

def copy_files(source_folder, dest_folder):
    """
    Copies files from source_folder to dest_folder and rebuilds extracted .data files.
    """
    if not os.path.exists(dest_folder):
        os.makedirs(dest_folder)

    # Look for extracted folders (textures, audio, etc.)
    extracted_base = os.path.join(source_folder, "extracted")
    if os.path.exists(extracted_base):
        for data_folder in os.listdir(extracted_base):
            folder_path = os.path.join(extracted_base, data_folder)
            if os.path.isdir(folder_path) and data_folder.endswith(".data"):
                out_file = os.path.join(dest_folder, data_folder)
                rebuild_from_extracted(out_file, folder_path)
                print(f"Rebuilt {out_file} from {folder_path}")

    # Copy any other files/folders from source_folder
    for filename in os.listdir(source_folder):
        source_path = os.path.join(source_folder, filename)
        dest_path = os.path.join(dest_folder, filename)
        if filename == "extracted":
            continue  # skip rebuilt folder
        if os.path.isfile(source_path):
            shutil.copy2(source_path, dest_path)
            print(f"Copied {filename} to {dest_folder}")
        elif os.path.isdir(source_path):
            shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
            print(f"Copied folder {filename} to {dest_folder}")

def patch_all_data_prefix(exe_path, new_prefix, output_path, log_file="searchfor.txt"):
    """
    Replaces all occurrences of 'data/' in the .exe with new_prefix (padded to 4 bytes).
    """
    if not (1 <= len(new_prefix) <= 4):
        raise ValueError("new_prefix must be 1 to 4 characters long")
    
    with open(exe_path, "rb") as f:
        data = bytearray(f.read())

    target = b"data/"
    padded_prefix = new_prefix.encode("utf-8").ljust(4, b'\x00')

    occurrences = 0
    i = 0
    while i < len(data):
        index = data.find(target, i)
        if index == -1:
            break
        data[index:index+4] = padded_prefix
        occurrences += 1
        i = index + 4  # continue searching after this replacement

    if occurrences == 0:
        print("No occurrences of 'data/' found in the file.")
    else:
        print(f"Replaced {occurrences} occurrences of 'data/' with '{new_prefix}'")

    with open(output_path, "wb") as f:
        f.write(data)

    with open(log_file, "w") as f:
        f.write(f"'{new_prefix}'\n")
    print(f"Patched file saved as {output_path} and logged in {log_file}")

def copy_selected_files(source_folder, dest_folder, filenames):
    """
    Copies only the specified files (by name) from source_folder to dest_folder.
    
    Args:
        source_folder (str): The folder to copy files from.
        dest_folder (str): The folder to copy files to.
        filenames (list[str]): List of file names to copy (exact matches).
    """
    if not os.path.exists(dest_folder):
        os.makedirs(dest_folder)

    for name in filenames:
        source_path = os.path.join(source_folder, name)
        dest_path = os.path.join(dest_folder, name)

        if os.path.exists(source_path):
            shutil.copy2(source_path, dest_path)
            print(f"Copied {name} → {dest_folder}")
        else:
            print(f"⚠️ File not found: {name}")

def create_texture(name):
    copy_files("assets", name)
    patch = input("Do you want to patch the .exe? (Y/N) ")
    if patch.lower() == "y":
        path = input("Where is the .exe file located? ")
        patch_all_data_prefix(path, name, "patched.exe")

def main():
    if not os.path.exists("assets"):
        copy_selected_files("data", "assets", ["shaders.data"])
        run("data/texture.data")
        run("data/audio.data")

    if len(sys.argv) < 2:
        print("Usage: python patch_texture.py -c <name> | -p <input.exe> <new_prefix> <output.exe>")
        sys.exit(1)

    if sys.argv[1] == "-p":
        if len(sys.argv) != 5:
            print("Usage: python patch_texture.py -p <input.exe> <new_prefix(1-4 chars)> <output.exe>")
            sys.exit(1)
        input_exe = sys.argv[2]
        new_prefix = sys.argv[3]
        output_exe = sys.argv[4]
        try:
            patch_all_data_prefix(input_exe, new_prefix, output_exe)
        except Exception as e:
            print(f"Error: {e}")
    elif sys.argv[1] == "-c":
        if len(sys.argv) != 3:
            print("Usage: python patch_texture.py -c <name>")
            sys.exit(1)
        name = sys.argv[2]
        create_texture(name)
    else:
        print("Unknown option", sys.argv[1])
        sys.exit(1)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class TexturePackBrowser(ctk.CTk):
    def __init__(self, base_path="."):
        super().__init__()
        self.title("Texture Pack Browser")
        self.geometry("600x400")

        self.base_path = base_path

        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=200)
        self.sidebar.pack(side="left", fill="y", padx=5, pady=5)

        self.sidebar_label = ctk.CTkLabel(
            self.sidebar, text="4-Letter Folders", font=ctk.CTkFont(size=15, weight="bold")
        )
        self.sidebar_label.pack(pady=(10, 5))

        # Folder list
        self.folder_listbox = ctk.CTkTextbox(self.sidebar, width=180, height=300)
        self.folder_listbox.pack(padx=5, pady=5)
        self.folder_listbox.configure(state="disabled")

        # Bind double-click
        self.folder_listbox.bind("<Double-1>", self.on_double_click)

        # Load folders
        self.load_folders()

    def load_folders(self):
        folders = [
            f
            for f in os.listdir(self.base_path)
            if os.path.isdir(os.path.join(self.base_path, f)) and len(f) == 4
        ]

        self.folder_listbox.configure(state="normal")
        self.folder_listbox.delete("1.0", "end")

        for folder in folders:
            self.folder_listbox.insert("end", folder + "\n")

        self.folder_listbox.configure(state="disabled")

    def on_double_click(self, event):
        index = self.folder_listbox.index("@%s,%s" % (event.x, event.y))
        folder_name = self.folder_listbox.get(f"{index} linestart", f"{index} lineend").strip()
        if folder_name:
            self.open_confirm_window(folder_name)

    def open_confirm_window(self, folder_name):
        popup = ctk.CTkToplevel(self)
        popup.title("Confirm Action")
        popup.geometry("300x150")
        popup.grab_set()  # focus popup

        label = ctk.CTkLabel(
            popup,
            text=f"Do you want to patch the .exe now?\n\nSelected pack: {folder_name}",
            justify="center",
        )
        label.pack(pady=20)

        # Button frame
        button_frame = ctk.CTkFrame(popup)
        button_frame.pack(pady=10)

        def yes_action():
            popup.destroy()
            messagebox.showinfo("Patching", f"Patching .exe with texture pack '{folder_name}'")
            # TODO: call your patching function here

        def no_action():
            popup.destroy()
            messagebox.showinfo("Skipped", "Patch cancelled.")

        yes_button = ctk.CTkButton(button_frame, text="Yes", width=100, command=yes_action)
        yes_button.grid(row=0, column=0, padx=10)

        no_button = ctk.CTkButton(button_frame, text="No", width=100, command=no_action)
        no_button.grid(row=0, column=1, padx=10)


if __name__ == "__main__":
    main()
