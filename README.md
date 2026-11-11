# Hive Breach

An original sci-fi 3D tower defense game. Alien swarms pour out of a crashed
hive ship and march toward the last colony base. Place laser, tesla, and
missile towers, then deploy the Aegis mech and steer it yourself.

Play in a mobile browser (portrait or landscape). Designed for iPhone.

## Play

Open the live GitHub Pages site, or serve the repo root locally:

```
python3 -m http.server 8080
```

Then visit `http://localhost:8080/`.

## How to play

1. Tap **Start Game**. Music begins after that first tap (iOS audio rule).
2. During the prep timer, tap a glowing pad to build the selected tower
   (Laser, Tesla, or Missile) using the buttons at the bottom.
3. Tap a tower to upgrade or sell it.
4. Press **Aegis** to drop the mech. Steer with the on-screen joystick or
   tap the ground to move. The mech stomps and fires until its energy runs out.
5. Hold the colony. If base health reaches zero, the run ends. Your best
   score is saved on this device.

## Build models

Blender 5 is used to author the GLB files:

```
/workspace/blender/blender -b -P scripts/build_models.py
```
