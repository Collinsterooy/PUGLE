from setuptools import find_packages, setup

package_name = 'pi_orientation_check'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Your Name',
    maintainer_email='you@example.com',
    description='ROS 2 bring-up check.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'hello_node = pi_orientation_check.hello_node:main',
            'orientation_check = pi_orientation_check.orientation_check:main',
        ],
    },
)
