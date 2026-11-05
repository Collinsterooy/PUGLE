# pi_orientation_check

Prints your Raspberry Pi's roll, pitch, and yaw from an IMU, so you can tilt the
board and watch the numbers move.

```
state    roll      pitch     yaw
ok       12.00     5.00      -30.00
```

This README goes from a fresh Ubuntu install to a running node, one step at a
time.

---

## What you need

| | |
| --- | --- |
| Board | Raspberry Pi 4 |
| OS | Ubuntu 22.04 (use 24.04 with `jazzy` instead of `humble`) |
| IMU | Any sensor with a ROS 2 driver that publishes `sensor_msgs/msg/Imu` |

Every command runs on the Pi.

---

## Step 1 — Install ROS 2

```bash
sudo apt update && sudo apt install -y locales curl gnupg lsb-release
sudo locale-gen en_US en_US.UTF-8
sudo add-apt-repository -y universe

sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

sudo apt update
sudo apt install -y ros-humble-ros-base ros-dev-tools

echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

Test it:

```bash
ros2 run demo_nodes_py talker
```

You should see `[INFO] [talker]: Publishing: 'Hello World: 1'` and counting up.
Ctrl-C to stop.

---

## Step 2 — Create the workspace

A workspace is a folder with a `src/` inside it. `colcon` expects that exact
shape.

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
```

```
~/ros2_ws/
└── src/          <- all packages go here
```

---

## Step 3 — Create the package with its dependencies

```bash
cd ~/ros2_ws/src
ros2 pkg create --build-type ament_python pi_orientation_check \
  --dependencies rclpy sensor_msgs std_msgs
```

That creates:

```
pi_orientation_check/
├── package.xml                       <- package name and dependencies
├── setup.py                          <- command names for ros2 run
├── setup.cfg                         <- install paths
├── resource/pi_orientation_check     <- empty marker file, do not delete
└── pi_orientation_check/             <- the Python code goes here
    └── __init__.py
```

The three dependencies:

| dependency | used for |
| --- | --- |
| `rclpy` | the ROS 2 Python library |
| `sensor_msgs` | the `Imu` message type |
| `std_msgs` | the `String` message type, used by the base node |

`--dependencies` writes them into `package.xml`. Open it and check:

```xml
<package format="3">
  <name>pi_orientation_check</name>
  <version>0.1.0</version>
  <description>ROS 2 bring-up check: prints Pi orientation from an IMU topic.</description>
  <maintainer email="you@example.com">Your Name</maintainer>
  <license>MIT</license>

  <exec_depend>rclpy</exec_depend>
  <exec_depend>sensor_msgs</exec_depend>
  <exec_depend>std_msgs</exec_depend>

  <export>
    <build_type>ament_python</build_type>
  </export>
</package>
```

Then open `setup.py` and make sure both nodes are listed under `entry_points`.
`ros2 run` only knows the commands listed here.

```python
    entry_points={
        'console_scripts': [
            'hello_node = pi_orientation_check.hello_node:main',
            'orientation_check = pi_orientation_check.orientation_check:main',
        ],
    },
```

If you add a node file and forget this list, `ros2 run` will not find it and the
build will not warn you.

---

## Step 4 — Add the node files

Copy both files from this repo into `~/ros2_ws/src/pi_orientation_check/pi_orientation_check/`:

| file | what it does |
| --- | --- |
| `hello_node.py` | Base node. Publishes a string once a second. |
| `orientation_check.py` | Reads the IMU and prints roll, pitch, yaw. |

```bash
cd ~/ros2_ws/src/pi_orientation_check/pi_orientation_check
ls
```

```
__init__.py  hello_node.py  orientation_check.py
```

The folder with the same name twice is normal: the outer one is the ROS package,
the inner one is the Python module.

---

## Step 5 — Build the workspace

```bash
cd ~/ros2_ws
colcon build --symlink-install
```

```
Starting >>> pi_orientation_check
Finished <<< pi_orientation_check [1.2s]
Summary: 1 package finished
```

Then source the workspace:

```bash
source install/setup.bash
```

You need this in every new terminal, or ROS will not find the package. To save
typing, add it to your shell once:

```bash
echo "source ~/ros2_ws/install/setup.bash" >> ~/.bashrc
```

Check the build found both nodes:

```bash
ros2 pkg executables pi_orientation_check
```

```
pi_orientation_check hello_node
pi_orientation_check orientation_check
```

If nothing prints, your `entry_points` and the build disagree. Rebuild.

---

## Step 6 — Run the base node

Terminal 1:

```bash
ros2 run pi_orientation_check hello_node
```

```
[INFO] [hello_node]: hello_node started, publishing on /hello
[INFO] [hello_node]: hello from hello_node (#0)
[INFO] [hello_node]: hello from hello_node (#1)
```

Terminal 2 (a second SSH session, with `source install/setup.bash` done):

```bash
ros2 topic echo /hello
```

```
data: 'hello from hello_node (#7)'
---
```

One process sending, another receiving. That means ROS 2 and your workspace both
work, so anything that fails after this is the IMU or its driver. Ctrl-C in both
terminals when done.

---

## Step 7 — Run the orientation check without an IMU

```bash
ros2 run pi_orientation_check orientation_check --fake
```

```
state    roll      pitch     yaw        extra
ok       0.00      0.00      0.00       q=( 0.00  0.00  0.00  1.00)  gyro d/s=( 0.0  0.0  18.8)
ok       2.41      4.64      3.76       q=( 0.02  0.04  0.03  1.00)  gyro d/s=( 0.0  0.0  18.6)
ok       4.22      8.82      7.46       q=( 0.03  0.08  0.06  0.99)  gyro d/s=( 0.0  0.0  18.1)
ok       4.99      12.14     11.04      q=( 0.03  0.11  0.09  0.99)  gyro d/s=( 0.0  0.0  17.4)
```

The numbers sweep up and down because the node is publishing fake motion and
reading it back. Ctrl-C to stop.

---

## Step 8 — Run it with the real IMU

Start the IMU driver first, then find its topic:

```bash
ros2 topic list
```

```
/imu/data
/parameter_events
/rosout
```

Check it is publishing:

```bash
ros2 topic hz /imu/data
```

```
average rate: 99.874
```

A number between 50 and 200 is normal. If nothing prints, the driver is not
running.

Then run the check on that topic:

```bash
ros2 run pi_orientation_check orientation_check --topic /imu/data
```

Tilt the Pi. Roll and pitch should follow your hands.

---

## Reading the output

| you see | meaning |
| --- | --- |
| `ok` | Working. The IMU reports a real orientation. |
| `tilt` | The IMU does not report orientation. Roll and pitch still work, yaw shows `n/a`. Fix with the filter below. |
| a checklist | No data arrived. See troubleshooting. |

Exit codes: `0` healthy, `1` no data, `2` ROS 2 not sourced in that shell.

### If you get `tilt`

Most bare IMU drivers publish `/imu/data_raw` with no orientation. Add a filter:

```bash
sudo apt install -y ros-humble-imu-tools
ros2 run imu_filter_madgwick imu_filter_madgwick_node --ros-args -p use_mag:=false
```

That subscribes `/imu/data_raw` and publishes `/imu/data` with orientation filled
in. Run step 8 again. Yaw will drift slowly without a magnetometer.

---

## Commands

| command | what it does |
| --- | --- |
| `--fake` | Fake motion, no hardware needed |
| `--topic /imu/raw` | Use a different topic (default `/imu/data`) |
| `--rate 2` | Print 2 times per second (default 5, `0` for every message) |
| `--timeout 30` | Wait 30 seconds for the first message (default 10) |

---

## Topics

| topic | type | direction |
| --- | --- | --- |
| `/hello` | `std_msgs/msg/String` | `hello_node` publishes |
| `/imu/data` (or `--topic`) | `sensor_msgs/msg/Imu` | `orientation_check` subscribes |
| same topic | `sensor_msgs/msg/Imu` | `orientation_check` publishes, only with `--fake` |

---

## Troubleshooting

| problem | fix |
| --- | --- |
| `ros2: command not found` | `source /opt/ros/humble/setup.bash` |
| `Package 'pi_orientation_check' not found` | `source ~/ros2_ws/install/setup.bash` |
| `ros2 pkg executables` prints nothing | Add the node to `entry_points` in `setup.py`, rebuild |
| `no messages on '/imu/data'` | `ros2 topic list` for the real name, and check the driver is running |
| Works on the Pi, not on your laptop | `export ROS_DOMAIN_ID=42` on both machines |
| Numbers frozen or jumpy | `ros2 topic hz` — the driver may be slow, or Wi-Fi is dropping packets |

---

## Repo layout

```
pi_orientation_check/
├── package.xml
├── setup.py
├── setup.cfg
├── resource/pi_orientation_check
└── pi_orientation_check/
    ├── __init__.py
    ├── hello_node.py
    └── orientation_check.py
```

## License

MIT.
