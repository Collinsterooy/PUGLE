#!/usr/bin/env python3
"""Print the Raspberry Pi's live orientation from a ROS 2 IMU topic.

Run:
    ros2 run pi_orientation_check orientation_check
    ros2 run pi_orientation_check orientation_check --fake
    ros2 run pi_orientation_check orientation_check --ros-args -p imu_topic:=/imu/raw

Exit codes: 0 healthy, 1 no data seen, 2 ROS 2 not sourced.
"""

import argparse
import math
import socket
import sys
import time

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
    from rclpy.utilities import remove_ros_args
    from sensor_msgs.msg import Imu
except ImportError:
    sys.stderr.write(
        '\nERROR: could not import rclpy / sensor_msgs.\n'
        'ROS 2 is not sourced in this shell. Run:\n'
        '    source /opt/ros/humble/setup.bash\n'
        '(use jazzy / iron / foxy if that is what you installed)\n\n'
    )
    sys.exit(2)


# --------------------------------------------------------------------------
# math helpers (no numpy on a fresh Pi image)
# --------------------------------------------------------------------------
def quat_to_euler_deg(x, y, z, w):
    """Quaternion (x, y, z, w) -> (roll, pitch, yaw) in degrees, ZYX order."""
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm < 1e-9:
        return None
    x, y, z, w = x / norm, y / norm, z / norm, w / norm

    roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))

    sinp = max(-1.0, min(1.0, 2.0 * (w * y - z * x)))
    pitch = math.asin(sinp)

    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))

    return tuple(math.degrees(a) for a in (roll, pitch, yaw))


def accel_to_tilt_deg(ax, ay, az):
    """Roll/pitch from the gravity vector alone. Yaw is unknowable here."""
    roll = math.atan2(ay, az)
    pitch = math.atan2(-ax, math.sqrt(ay * ay + az * az))
    return math.degrees(roll), math.degrees(pitch)


def has_valid_orientation(msg):
    """A covariance of -1 is the ROS convention for 'orientation not provided'."""
    if msg.orientation_covariance[0] < 0.0:
        return False
    q = msg.orientation
    return (q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w) > 1e-6


def quat_from_rpy(roll_rad, pitch_rad, yaw_rad):
    """(roll, pitch, yaw) radians -> quaternion (x, y, z, w)."""
    cr, sr = math.cos(roll_rad / 2.0), math.sin(roll_rad / 2.0)
    cp, sp = math.cos(pitch_rad / 2.0), math.sin(pitch_rad / 2.0)
    cy, sy = math.cos(yaw_rad / 2.0), math.sin(yaw_rad / 2.0)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


# --------------------------------------------------------------------------
# the node
# --------------------------------------------------------------------------
class OrientationCheck(Node):
    def __init__(self, cli):
        super().__init__('orientation_check')

        # command-line flags become the parameter defaults, so a
        # `-p name:=value` override still wins over the flag.
        self.declare_parameter('imu_topic', cli.topic)
        self.declare_parameter('rate', cli.rate)
        self.declare_parameter('timeout', cli.timeout)
        self.declare_parameter('fake', cli.fake)

        self.topic = self.get_parameter('imu_topic').value
        rate_hz = float(self.get_parameter('rate').value)
        self.timeout_s = float(self.get_parameter('timeout').value)
        self.fake = bool(self.get_parameter('fake').value)

        self.print_period = 1.0 / rate_hz if rate_hz > 0 else 0.0
        self.count = 0
        self.first_seen = None
        self.last_print = 0.0
        self.started_at = time.monotonic()
        self.done = False
        self.fake_t0 = self.started_at

        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        # the subscription is always created: in fake mode the node listens to
        # its own publisher, so the lines on screen travel the real DDS path.
        self.create_subscription(Imu, self.topic, self.on_imu, qos)

        if self.fake:
            self.fake_pub = self.create_publisher(Imu, self.topic, qos)
            self.create_timer(1.0 / 50.0, self.publish_fake)
        else:
            self.create_timer(1.0, self.check_timeout)

        self.banner()

    def banner(self):
        log = self.get_logger()
        log.info('-' * 62)
        log.info('host   : %s' % socket.gethostname())
        log.info('python : %s' % sys.version.split()[0])
        try:
            from rclpy.utilities import get_rmw_implementation_identifier
            log.info('rmw    : %s' % get_rmw_implementation_identifier())
        except Exception:
            pass
        log.info('topic  : %s' % self.topic)
        log.info('mode   : %s' % ('FAKE (synthetic motion)' if self.fake else 'live'))
        log.info('-' * 62)
        log.info('%-8s %-9s %-9s %-9s  %s' % ('state', 'roll', 'pitch', 'yaw', 'extra'))

    # -- real IMU -----------------------------------------------------------
    def on_imu(self, msg):
        self.count += 1
        if self.first_seen is None:
            self.first_seen = time.monotonic()

        now = time.monotonic()
        if self.print_period and (now - self.last_print) < self.print_period:
            return
        self.last_print = now

        gx = math.degrees(msg.angular_velocity.x)
        gy = math.degrees(msg.angular_velocity.y)
        gz = math.degrees(msg.angular_velocity.z)

        if has_valid_orientation(msg):
            rpy = quat_to_euler_deg(
                msg.orientation.x, msg.orientation.y,
                msg.orientation.z, msg.orientation.w,
            )
            if rpy is None:
                return
            roll, pitch, yaw = rpy
            state = 'ok'
            extra = 'q=(% .2f % .2f % .2f % .2f)  gyro d/s=(% .1f % .1f % .1f)' % (
                msg.orientation.x, msg.orientation.y, msg.orientation.z,
                msg.orientation.w, gx, gy, gz,
            )
        else:
            roll, pitch = accel_to_tilt_deg(
                msg.linear_acceleration.x,
                msg.linear_acceleration.y,
                msg.linear_acceleration.z,
            )
            yaw = None
            state = 'tilt'
            extra = 'no fused orientation; roll/pitch from accel only'

        print(
            '%-8s %-9.2f %-9.2f %-9s  %s'
            % (state, roll, pitch, 'n/a' if yaw is None else '%.2f' % yaw, extra),
            flush=True,
        )

    # -- fake motion --------------------------------------------------------
    def publish_fake(self):
        t = time.monotonic() - self.fake_t0
        msg = Imu()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'imu_link'

        yaw = math.radians(30.0 * math.sin(2.0 * math.pi * 0.10 * t))
        pitch = math.radians(15.0 * math.sin(2.0 * math.pi * 0.25 * t))
        roll = math.radians(5.0 * math.sin(2.0 * math.pi * 0.40 * t))

        x, y, z, w = quat_from_rpy(roll, pitch, yaw)
        msg.orientation.x, msg.orientation.y = x, y
        msg.orientation.z, msg.orientation.w = z, w
        msg.orientation_covariance[0] = 0.01

        msg.angular_velocity.z = math.radians(30.0) * 2.0 * math.pi * 0.10 * math.cos(
            2.0 * math.pi * 0.10 * t
        )
        msg.linear_acceleration.z = 9.81
        self.fake_pub.publish(msg)

    # -- watchdog -----------------------------------------------------------
    def check_timeout(self):
        if self.first_seen is not None or self.done:
            return
        if (time.monotonic() - self.started_at) < self.timeout_s:
            return
        log = self.get_logger()
        log.error("no messages on '%s' after %.0fs." % (self.topic, self.timeout_s))
        log.error('checklist:')
        log.error('  1. ros2 node list                # is the driver running?')
        log.error('  2. ros2 topic list               # what is the topic called?')
        log.error('  3. ros2 topic hz <topic>         # is it publishing?')
        log.error('  4. ros2 topic info <topic>       # is it sensor_msgs/msg/Imu?')
        log.error('  5. echo $ROS_DOMAIN_ID           # same on every machine?')
        log.error('  6. rerun with --fake             # to test ROS 2 without hardware')
        self.done = True


def parse_args(argv):
    ap = argparse.ArgumentParser(
        description="Print the Raspberry Pi's orientation from a ROS 2 IMU topic."
    )
    ap.add_argument('--topic', default='/imu/data',
                    help='IMU topic to subscribe to (default: /imu/data)')
    ap.add_argument('--rate', type=float, default=5.0,
                    help='prints per second, 0 for every message (default: 5)')
    ap.add_argument('--timeout', type=float, default=10.0,
                    help='seconds to wait for the first message (default: 10)')
    ap.add_argument('--fake', action='store_true',
                    help='publish synthetic motion instead of waiting for a real IMU')
    return ap.parse_args(argv)


def main(argv=None):
    # strip --ros-args ... so argparse does not choke on ROS's own flags
    raw = remove_ros_args(args=sys.argv if argv is None else [sys.argv[0]] + argv)
    cli = parse_args(raw[1:])

    rclpy.init()
    node = OrientationCheck(cli)
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.1)
            if not node.fake and node.done:
                return 1
    except KeyboardInterrupt:
        pass
    finally:
        node.get_logger().info('received %d messages total' % node.count)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    return 0 if (node.fake or node.count > 0) else 1


if __name__ == '__main__':
    sys.exit(main())
