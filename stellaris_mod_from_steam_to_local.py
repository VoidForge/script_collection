import glob
import re
from pathlib import Path

'''
This script creates metadata .mod files in Stellaris/mod so that liberty-version stellaris
can recognize steam-downloaded mods.
Place steam downloaded mods in Stellaris/mod, write the correct MOD_DIR_PATH, 
and run the script to generate .mod files. 
Tested for Stellaris v3.12.5

maybe no longer necessary for irony mod manager?
'''

MOD_DIR_PATH = Path(r'C:\Users\admin\Documents\Paradox Interactive\Stellaris\mod')

for entry in glob.iglob(str(MOD_DIR_PATH / '*')):
    subdir = Path(entry)

    # Skip non-directories (e.g., existing .mod files, loose files)
    if not subdir.is_dir():
        continue

    try:
        descriptor_path = subdir / "descriptor.mod"
        with open(descriptor_path, encoding='utf-8') as f:
            lines = f.readlines()

        # Remove any existing path= line
        path_loc = None
        for i in range(len(lines)):
            if re.match(r'path', lines[i]) is not None:
                path_loc = i
        if path_loc is not None:
            lines.pop(path_loc)

        # Append the corrected local path (Paradox games expect forward slashes)
        lines.append(f'\npath="{subdir.as_posix()}"')

        # Write the .mod file in the mod root directory (skip if already exists)
        output_path = MOD_DIR_PATH / f"{subdir.name}.mod"
        if output_path.exists():
            print(f"Skipping '{subdir.name}': .mod file already exists")
            continue
        with open(output_path, mode='w', encoding='utf-8') as modinfof:
            modinfof.writelines(lines)
            print(f"Created '{output_path.name}' for mod '{subdir.name}'")

    except FileNotFoundError:
        print(f"Skipping '{subdir.name}': no descriptor.mod found (not a mod folder)")
    except PermissionError as e:
        print(f"Error processing '{subdir.name}': permission denied — {e}")
    except UnicodeDecodeError as e:
        print(f"Error processing '{subdir.name}': encoding issue — {e}")
    except OSError as e:
        print(f"Error processing '{subdir.name}': {e}")
 