# VEX V5 Reader

A Claude skill that reads VEX V5 robot code and explains what it does.

VEXcode saves projects as JSON, so opening one shows a single huge line of escaped C++ or raw block XML. This skill decodes those files, lists the robot's devices and ports, and gives Claude notes on the VEXcode and PROS behavior that most often causes bugs.

## What it reads

| Source | What you get |
|---|---|
| `.v5cpp`, `.v5python` | Numbered code matching VEXcode's line numbers, plus a device list |
| `.v5blocks` | Readable steps for each stack of blocks, including My Blocks and comments |
| PROS project | Libraries, your source files, devices and entry points, skipping library files |
| VS Code VEX project | Your source files, devices and entry points |

It also flags two devices on one port, code that disagrees with VEXcode's Devices panel, and block stacks with no event on top. It can compare two versions of a project too.

## Install

Clone it into your Claude Code skills folder:

```bash
git clone https://github.com/Tyrese-mp3/vex-v5-reader.git ~/.claude/skills/vex-v5-reader
```

It needs Python 3 and no extra packages. It has been tested on Python 3.14.

## Use

Ask Claude about your robot code, or type `/vex-v5-reader`. For example: "why does my claw not work in `CompFinal.v5cpp`?"

You can also run the reader by itself:

```bash
python scripts/vex_read.py "robot.v5cpp"
python scripts/vex_read.py "old.v5cpp" --diff "new.v5cpp"
python scripts/vex_read.py "path/to/pros-project"
```

Add `--summary` for just the devices and checks, or `--full` to include generated setup code.

## Limits

- It is read-only. It never changes your files, and it does not compile code or run it on a robot.
- Block support was tested on a small number of real projects. Handling of if/else blocks has only been tested on a made-up sample.
- `.v5python` support has only been tested on a small made-up file.

This is an unofficial project, not affiliated with VEX Robotics or the PROS team.
