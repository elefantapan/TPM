# TPM
Texture pack manager for Incredicer
# Installation

You can only [Use the source code](#usesource) right now

# Use source
1. Download python [here](https://www.python.org/downloads/)
2. Dowload the source code by pressing code and then download zip.
3. Extract main.py
4. Move the main.py to the game files (So the folder where the .exe is)
5. Run it by doing `python main.py`. You should see an assets folder
## Done!



# Usage
There are three commands/flags. 
1. python `main.py -p <input.exe> <new_prefix> <output.exe>`
   This patches the Incredicer.exe to your desiered texture pack.
2. `python main.py -c <name>`
  This creates a texture pack with your desired name. If you want to edit the textures they are in assets/extracted/texture.data/0000_len_219697.png. The font is in assets/extracted/texture.data/0001_len_6769.png (Shader support will come soon.)
3. When you first start the program itl create an assets folder. (`python main.py`)

# Creating a texture pack
## Editing textures
Go to `assets/extracted/texture.data/` open `0000_len_219697.png` Now you can edit all the textures.
## Editing audio.
Go to `assets/extracted/audio.data/` and there are all of the sounds. (Pretty shure they need to be the same lenght but not sure)
