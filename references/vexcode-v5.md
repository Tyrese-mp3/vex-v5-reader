# VEXcode V5 notes

API facts here were checked against the V5 SDK headers, version `V5_20240802_15_00_00`. Items marked *(VEX practice)* come from general VEX knowledge, not the headers.

For an exact signature, the VS Code VEX extension keeps the SDK at `%APPDATA%\Code\User\globalStorage\vexrobotics.vexcode\sdk\cpp\V5\<version>\vexv5\include\` on Windows. Search `vex_motor.h`, `vex_motorgroup.h`, `vex_drivetrain.h`, `vex_smartdrive.h`, `vex_controller.h`, `vex_competition.h`, `vex_triport.h` and `vex_imu.h`.

## Contents

- Generated section
- Program flow
- Units and ranges
- What waits and what does not
- Blocks projects
- Common problems

## Generated section

Everything before `#pragma endregion VEXcode Generated Robot Configuration` comes from VEXcode's Devices panel. It normally declares devices and defines `vexcodeInit()`, which calibrates the drivetrain's inertial sensor.

It can also hold real driver controls. Binding a device to buttons or joysticks in the Devices panel generates `rc_auto_loop_function_Controller1`, started as a background task while the program loads. For example, binding R1/R2 to a lift spins it with no code in `main`. These controls run whenever `RemoteControlCodeEnabled` is true. The script shows this section whenever it reads the controller.

The Devices panel is stored as `robotConfig` (`rconfig` in older files). If its ports disagree with the code, the code is what compiles from the saved file, but VEXcode may rewrite the generated section from the panel, so the two should be made to match.

## Program flow

A competition program usually looks like this:

```cpp
competition Competition;
int main() {
  vexcodeInit();
  Competition.autonomous(autonomous);
  Competition.drivercontrol(userControl);
  preAutonomous();
  while (true) { wait(100, msec); }
}
```

- `autonomous` and `userControl` run only when competition control starts those periods. A function named `autonomous` that is never registered or called does not run.
- `Competition.isEnabled()`, `isDriverControl()` and `isAutonomous()` report the current state.
- `main` must not exit, which is what the final loop is for.
- A `task` or `thread` started in `main` runs alongside everything else. The flags `competition::bStopTasksBetweenModes` and `bStopAllTasksBetweenModes` control what stops when the mode changes.

## Units and ranges

| Item | Meaning |
|---|---|
| `Axis.position()` | -100 to 100 percent by default |
| `Axis.value()` | -127 to 127 |
| `Axis1`, `Axis2` | Right stick horizontal, vertical *(VEX practice)* |
| `Axis3`, `Axis4` | Left stick vertical, horizontal *(VEX practice)* |
| `ratio36_1` | Red cartridge, 100 rpm |
| `ratio18_1` | Green cartridge, 200 rpm |
| `ratio6_1` | Blue cartridge, 600 rpm |

`smartdrive(left, right, gyro, wheelTravel, trackWidth, wheelBase, units, externalGearRatio)` declares a drivetrain. `wheelTravel` is the wheel's circumference, so 319.19 mm is a 4 inch wheel.

Three-wire ports are lettered A to H. The Devices panel stores them as numbers, so 2 means B and 8 means H.

`digital_out.set(bool)` sets the output high or low. Whether high extends a piston depends on the tubing.

## What waits and what does not

| Call | Behavior |
|---|---|
| `spin(dir)`, `spin(dir, speed, units)`, `stop()` | Returns immediately |
| `driveFor`, `turnFor` | Waits until finished unless the last argument is `false` |
| `spinFor` by rotation, `spinToPosition` | Waits until finished unless the last argument is `false` |
| `spinFor` by time | Always waits, and has no such argument |
| `wait(20, msec)` | Pauses this task only |

`spin(dir)` with no speed uses the most recent `setVelocity` value. `setDriveVelocity` and `setTurnVelocity` apply only to Drivetrain commands, so they do not change a direct `motor_group.spin(...)` call.

## Blocks projects

The script prints each stack of blocks as indented lines. Block type names follow `v5_<category>_<action>`:

| Seen in real projects | Meaning |
|---|---|
| `v5_events_when_started`, `v5_events_when_autonomous`, `v5_events_when_controller_button` | Event blocks that start a stack |
| `v5_control_forever`, `v5_control_repeat`, `v5_control_if_then_else`, `v5_control_wait`, `v5_control_stop_project` | Loops, branches and timing |
| `v5_motion_spin`, `v5_motion_set_motor_velocity` | Motor commands |
| `v5_sensing_set_digital_out`, `v5_sensing_position_of_controller` | Three-wire output and joystick reading |
| `v5_variables_set_variable`, `v5_operator_add`, `v5_operator_subtract` | Variables and math |
| `v5_looks_print`, `v5_looks_draw_rectangle` | Brain screen output |
| `define ...`, `call ...` | A My Block and a use of it, printed with its parameters filled in |
| `# text` | A comment block |

Other types use the same pattern, so read them by name. If a meaning is unclear, say so rather than guess.

- A stack with no event block on top does not run. The script labels these stacks.
- Stacks under separate `when started` blocks run at the same time *(VEX practice)*, so two stacks commanding one motor will conflict.
- A Blocks project stores no generated code, only the blocks themselves.

## Common problems

- **Two places command one motor.** A motor bound in the Devices panel is also driven by the generated loop. If user code also commands it, they fight and the motor stutters or ignores one of them.
- **A waiting call inside the driver loop.** `spinFor` or `driveFor` without `false` freezes the joysticks until it finishes.
- **A `while (true)` loop with no `wait`.** It starves other tasks. Loops normally wait about 20 ms *(VEX practice)*.
- **Sign flips stacking up.** A motor's reversed flag, `spin(reverse, ...)` and a negated joystick each flip direction. Count every flip before saying which way something goes.
- **`.pressed(fn)` inside a loop.** It sets up a callback, so it belongs before the loop and runs once *(VEX practice)*.
- **Moving during inertial calibration.** `calibrate()` needs the robot still, and turns are unreliable if the program moves before `isCalibrating()` turns false *(VEX practice)*.
- **Autonomous stuck on one step.** `driveFor` can wait forever if the robot is blocked. `setTimeout` limits the wait *(VEX practice)*.
- **Testing without competition control.** Competition callbacks need a competition switch, the field, or the controller's timed run *(VEX practice)*.
