from PIL import Image 
import numpy as np
import rospy
from geometry_msgs.msg import Twist
from sensor_msgs.msg import LaserScan

class Simulator:
    def __init__(self, filename, resolution, laser_min_angle, laser_max_angle, laser_resolution, laser_max_dist):
        img = Image.open(filename)
        img = img.convert('1')
        self.gridmap = 1.0 - np.asarray(img)
        self.gridmap = np.around(self.gridmap)
        self.resolution = resolution   # map resolution
        self.laser_min_angle = laser_min_angle    #degree
        self.laser_max_angle = laser_max_angle    #degree
        self.laser_resolution = laser_resolution  #degree
        self.laser_max_dist = laser_max_dist      #meter
        self.robot_x = 0.0                        #meter
        self.robot_y = 0.0                        #meter
        self.robot_theta = 0.0                    #radian  

    def to_xy (self, i, j):
        x = j * self.resolution
        y = (self.gridmap.shape[0] - i) * self.resolution
        return x, y

    def to_ij (self, x, y):
        i = self.gridmap.shape[0] - (y / self.resolution)
        j = x / self.resolution
        return int(i), int(j)

    def is_inside (self, i, j):
        return i<self.gridmap.shape[0] and j<self.gridmap.shape[1] and i>=0 and j>=0

    def get_borders(self):
        return [0.0, self.gridmap.shape[1] * self.resolution, 0.0, self.gridmap.shape[0] * self.resolution]

    def set_robot_pos(self, x, y, theta):
        self.robot_x = x
        self.robot_y = y
        self.robot_theta = theta

    def get_measurements(self, debug=False):
        laser_data = []
        for i in range(self.laser_min_angle, self.laser_max_angle+1, self.laser_resolution):
            xp, yp, is_hit = self.raycast(self.robot_x, self.robot_y, np.radians(i) + self.robot_theta, self.laser_max_dist, debug)
            if is_hit:
                laser_data.append(np.sqrt((xp-self.robot_x)**2+(yp-self.robot_y)**2))
            else:
                laser_data.append(self.laser_max_dist)
        return np.array(laser_data)

    def raycast(self, x0, y0, theta, max_dist, debug=False):    #x0, y0, max_dist in meters; theta in radian;  debug is for visulizations
        x1 = x0 + max_dist*np.cos(theta)
        y1 = y0 + max_dist*np.sin(theta)
        i0, j0 = self.to_ij(x0, y0)
        i1, j1 = self.to_ij(x1, y1)
        max_dist_cells = max_dist / self.resolution
        ip, jp, is_hit = self.bresenham(i0, j0, i1, j1, max_dist_cells, debug)
        xp, yp = self.to_xy(ip, jp)
        return xp, yp, is_hit
    
    #bresenham method is used to plot the lines (see references)
    def bresenham (self, i0, j0, i1, j1, max_dist_cells, debug=False):   # i0, j0 (starting point)
        dx = np.absolute(j1-j0)
        dy = -1 *  np.absolute(i1-i0)
        
        sx = -1
        if j0<j1:
            sx = 1

        sy = -1
        if i0<i1:
            sy = 1

        jp, ip = j0, i0
        err = dx+dy                     # error value e_xy
        while True:                     # loop

            if (jp == j1 and ip == i1) or (np.sqrt((jp-j0)**2+(ip-i0)**2) >= max_dist_cells) or not self.is_inside(ip, jp):  
                return ip, jp, False
            elif self.gridmap[int(ip)][int(jp)]==1:
                return ip, jp, True

            if debug:
                self.gridmap[int(ip)][int(jp)] = 0.5

            e2 = 2*err
            if e2 >= dy:                # e_xy+e_x > 0 
                err += dy
                jp += sx
            
            if e2 <= dx:                # e_xy+e_y < 0
                err += dx
                ip += sy

class SimulatorROS:
    def __init__(self):
        dt = 0.1
        resolution = 0.1
        laser_min_angle = -135
        laser_max_angle=135
        laser_resolution=1
        laser_max_dist=50.0

        simulator = Simulator("map.png", resolution, laser_min_angle, laser_max_angle, laser_resolution, laser_max_dist)
        simulator.set_robot_pos(1.5, 1.5, np.radians(45)) # robot start point

        self.cmdvel_queue = []

        rospy.init_node('RosSimulator', anonymous=True)
        laser_pub = rospy.Publisher('scan', LaserScan, queue_size=10)
        rospy.Subscriber("cmd_vel", Twist, cmdvel_callback)

    def publish_laserscan(self, data):
        scan = LaserScan()
        scan.header.frame_id = "laser"
        scan.header.stamp = rospy.Time().now()
        scan.angle_min = np.radians(laser_min_angle)
        scan.angle_max = np.radians(laser_max_angle)
        scan.angle_increment = np.radians(laser_resolution)
        scan.range_max = laser_max_dist
        scan.ranges = data
        laser_pub.publish(scan)

    def process_cmdvel(self, cmdvel_list):
        if len(cmdvel_list)>0:
            new_dt = dt / len(cmdvel_list)
            for i in cmdvel_list:
                simulator.robot_theta += i['ang'] * new_dt
                simulator.robot_x += i['lin'] * np.cos(simulator.robot_theta) * new_dt
                simulator.robot_y += i['lin'] * np.sin(simulator.robot_theta) * new_dt
            self.cmdvel_queue = []

    def cmdvel_callback(self, data):
        self.cmdvel_queue.append({'lin': data.linear.x, 'ang': data.angular.z})



rate = rospy.Rate(1.0/dt)
while not rospy.is_shutdown():
    process_cmdvel(cmdvel_queue)
    publish_laserscan( simulator.get_measurements(debug=True) )
    rate.sleep()