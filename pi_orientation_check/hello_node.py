"""Base node: the smallest thing that proves ROS 2 works.

Run:  ros2 run pi_orientation_check hello_node
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class HelloNode(Node):
    def __init__(self):
        super().__init__('hello_node')
        self.pub = self.create_publisher(String, 'hello', 10)
        self.count = 0
        self.timer = self.create_timer(1.0, self.tick)
        self.get_logger().info('hello_node started, publishing on /hello')

    def tick(self):
        msg = String()
        msg.data = 'hello from %s (#%d)' % (self.get_name(), self.count)
        self.count += 1
        self.pub.publish(msg)
        self.get_logger().info(msg.data)


def main():
    rclpy.init()
    node = HelloNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
