# PROS notes

API facts here were checked against PROS kernel 4.2.2 headers. Items marked *(PROS practice)* come from general knowledge, not the headers.

The script prints the project's kernel version. PROS 3 differs in places, for example `pros::Motor_Group` and `pros::ADIDigitalOut`. For an exact signature, search the project's own `include/pros/*.hpp`, which always matches its kernel. `motors.hpp`, `motor_group.hpp`, `misc.hpp`, `adi.hpp`, `imu.hpp` and `rtos.hpp` are the most useful.

## Contents

- Project layout
- Program flow
- Devices
- Motion commands
- Common problems

## Project layout

| Path | Contents |
|---|---|
| `src/` | The team's code |
| `include/` | The team's headers, plus PROS and library headers |
| `project.pros` | Project name, kernel and library versions |
| `firmware/`, `bin/`, `.d/` | Compiled libraries and build output, not worth reading |

Only C and C++ source files are compiled. A `.v5cpp` left in `src/` is ignored by the build.

## Program flow

PROS calls these functions, so a PROS program has no `main()`:

| Function | When it runs |
|---|---|
| `initialize()` | Once at program start. Other modes wait until it returns *(PROS practice)* |
| `disabled()` | While the robot is disabled |
| `competition_initialize()` | After `initialize()`, when connected to the field or a competition switch |
| `autonomous()` | During the autonomous period. Stopped if the robot is disabled, and restarts from the top when re-enabled |
| `opcontrol()` | During driver control. Runs right after `initialize()` when no competition control is connected |

`autonomous()` does not run on its own without a competition switch or the field, though it can be called from `opcontrol()` to test it.

`main.h` defines `PROS_USE_SIMPLE_NAMES`, so `ANALOG_LEFT_Y` and `DIGITAL_L1` are short for the longer `pros::E_CONTROLLER_...` names.

## Devices

- A negative port means reversed: `pros::MotorGroup right_mg({-14, -15})` reverses both motors, which is the usual way to reverse a side.
- `set_reversed(bool, index = 0)` changes **one** motor, the first by default. `set_reversed_all(bool)` changes all of them. So `left_mg.set_reversed(true)` on a two-motor group reverses only the first motor.
- The same index rule applies to other group functions with an `_all` version. Check the header before assuming a call affects the whole group.
- `MotorGroup` and `Motor` take an optional gearset. If it is left out, the code does not set one.
- `pros::adi::DigitalOut p('A')` is a three-wire output, set with `set_value(bool)`. `pros::adi::Pneumatics` adds `extend()`, `retract()` and `toggle()`.
- `pros::Imu.reset(blocking = false)` starts calibration and returns right away unless `true` is passed. Moving before `is_calibrating()` turns false gives bad headings.

## Motion commands

Every motion command returns immediately. The motor keeps doing the last thing it was told until told otherwise, so timing comes from `pros::delay()`.

| Call | Meaning |
|---|---|
| `move(v)` | Voltage from -127 to 127. Matches `get_analog()` directly |
| `move_velocity(rpm)` | Speed held by the motor: up to 100 red, 200 green, 600 blue |
| `move_voltage(mV)` | Voltage in millivolts |
| `move_relative(pos, rpm)` | Move a distance in encoder units. Does not wait |
| `move_absolute(pos, rpm)` | Move to a position in encoder units. Does not wait |
| `brake()` | Stop using the current brake mode |

Controller readings:

- `get_analog()` returns -127 to 127.
- `get_digital()` returns 1 while a button is held.
- `get_digital_new_press()` returns 1 once per press, and only if the button was not pressed the last time it was called for that button.

## Common problems

- **Nested button checks.** `get_digital_new_press` is true only on the pass where a press first appears, so a check nested inside another almost never runs. Each button needs its own top-level `if`.
- **A press lost to another reader.** `get_digital_new_press` is not thread-safe. Only one task should poll a given button.
- **Reversing only part of a group.** See `set_reversed` above. The motors on one side then work against each other.
- **A motor left running.** Without a stop, `move_velocity` carries on through a `pros::delay()` and into the next step. In autonomous, check what each motor is doing during every delay.
- **Sides started at different times.** A long delay between the left and right commands makes the robot spin instead of driving straight.
- **Waiting in `opcontrol` for a motion to finish.** A long `pros::delay` there freezes the joysticks.
- **A `while (true)` loop with no `pros::delay`.** Other tasks are starved. Loops normally delay a few milliseconds *(PROS practice)*.
- **Too much work in `initialize()`.** A long routine holds up everything else *(PROS practice)*.
- **Libraries.** LemLib or EZ-Template appear under the project's libraries. Their headers are in `include/`, and their functions may block where plain PROS calls do not.
