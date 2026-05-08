# Unibot

Unibot is a Python-based game hack that works on numerous games because its features don't depend on reading memory. Its configuration file can easily be modified to make it work on any FPS game that has an enemy highlight color such as VALORANT and Overwatch.   

Unibot sends mouse input to assist you in aiming and shooting. Three different mouse input methods have been implemented, and adding another requires only around 20 lines of code.  

Unibot was created as a PoC hobby project that proved that multimillion dollar anti-cheats such as Riot Games' Vanguard could be bypassed by a simple Python script that does not touch any game memory, and instead detects enemies by screengrabbing the user's monitor. 

Currently implemented input methods:  
- **Windows API**  
- **Interception driver** (https://github.com/oblitum/Interception)  
- **External hardware** capable of simulating a human interface device, such as an Arduino Leonardo or any Raspberry Pi Pico variant

Unibot can communicate with these microcontrollers through a COM port or a socket connection (Ethernet or Wi-Fi).

## What it does

### Aim assist
- Detects targets by analyzing pixels within a specified color range on your screen
- Automatically moves the aim towards the detected target

### Triggerbot
- Automatically shoots when the player's crosshair is on a target

### Rapid-fire
- Clicks rapidly to automatically shoot semi-automatic weapons

### Recoil Mitigation
- Counters weapon recoil
- Supports multiple recoil systems:
  - **Point-and-shoot**: Bullets go where your crosshair looks
  - **Offset type recoil**: Bullets go above crosshair
  
## Disclaimer
  
This is a hobby project and intended for learning purposes only. I do not condone cheating in any regard. 

If you are using Unibot to cheat, please take a moment to reflect on why. Cheating ruins competitive integrity, undermines genuine achievement, and leaves you feeling just as empty as before.