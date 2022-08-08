#!/usr/bin/env python3
import numpy as np
import random
import argparse
import math
from statistics import mean
import matplotlib.pyplot as plt
from PIL import Image
from datetime import datetime
from roboticstoolbox import DistanceTransformPlanner, PRMPlanner
from linear_path import LinearPath

import rospy
from std_msgs.msg import Float64MultiArray
from nav_msgs.msg import OccupancyGrid
from smit_matlab_sim.srv import Step, AddPedestrian, AddPedestrianResponse
from std_srvs.srv import Empty

class RandomMapServerNode(object):
	"""docstring for RandomMapServerNode"""
	def __init__(self, args):
		self.rms = RandomMapServerWithPedestrians(args)
		self.pub = rospy.Publisher('map', OccupancyGrid, queue_size=10)
		self.srv_step = rospy.Service('perform_pedestrians_step', Step, self.perform_step)
		self.srv_regenerate = rospy.Service('regenerate_map', Empty, self.regenerate_map)
		self.srv_add_ped = rospy.Service('add_pedestrian', AddPedestrian, self.add_pedestrian)

		self.publish = args.publish
		self.rate = args.publish_rate
		self.auto_step = args.auto_step
		self.pub_on_step = args.publish_on_step

		self.msg = OccupancyGrid()
		self.msg.header.frame_id = "map"
		self.msg.info.width = self.rms.w
		self.msg.info.height = self.rms.h
		self.msg.info.resolution = self.rms.res
		self.msg.info.map_load_time = rospy.Time.now()
		self.msg.info.origin.position.x = 0
		self.msg.info.origin.position.y = 0
		self.msg.info.origin.position.z = 0
		self.msg.info.origin.orientation.x = 0
		self.msg.info.origin.orientation.y = 0
		self.msg.info.origin.orientation.z = 0
		self.msg.info.origin.orientation.w = 1

		if self.publish:
			self.timer = rospy.Timer(rospy.Duration(1.0/self.rate), self.publish_map)

	def perform_step(self, req):
		self.rms.step(req.time)
		if self.pub_on_step:
			self.publish_map()

	def add_pedestrian(self, req):
		if len(req.path.layout.dim) == 2 and req.path.layout.dim[1].size == 2:
			path = []
			for i in range(req.path.layout.dim[0].size):
				path.append([req.path.data[req.path.layout.data_offset + req.path.layout.dim[1].stride*i], req.path.data[req.path.layout.data_offset + req.path.layout.dim[1].stride*i + 1]])
			self.rms.add_pedestrian(req.velocity, np.array(path), req.full_path, req.circle)
			return AddPedestrianResponse(True)
		else:
			return AddPedestrianResponse(False)


	def publish_map(self, event = None):
		self.msg.data = np.uint8(self.rms.get_pedmap().reshape(-1)*100)
		self.msg.header.stamp = rospy.Time.now()
		self.pub.publish(self.msg)
		if (self.auto_step):
			self.rms.step(1.0/self.rate)

	def regenerate_map(self, req):
		self.rms.regenerate_map()

class RandomMapServerWithPedestrians(object):
	"""docstring for RandomMapServerWithPedestrians"""
	def __init__(self, args):
		self.res = args.resolution
		self.w = round(args.width/self.res)
		self.h = round(args.height/self.res)

		self.wall_w = round(args.wall_width/self.res)
		print("Original wall width: " + str(args.wall_width))
		print("Resolution: " + str(self.res))
		print("Wall width: " + str(self.wall_w))
		self.ext_wall = args.external_wall
		self.min_room_dim = round(args.min_room_dim/self.res)
		self.door_w = round(args.door_width/self.res)
		self.door_to_wall_min = round(args.door_to_wall_min/self.res)
		self.max_depth = args.max_depth
		
		self.map = np.empty((self.h, self.w))

		self.num_p = args.num_of_pedestrians
		self.p_min_sp = args.pedestrian_min_speed/self.res
		self.p_max_sp = args.pedestrian_max_speed/self.res
		self.p_rad = round(args.pedestrian_radius/self.res)
		self.foot_rad = round(args.pedestrian_foot_radius/self.res)
		self.p_circles = args.pedestrian_walk_circles

		if self.num_p > 0:

			# self.planner = DistanceTransformPlanner(self.map, distance = 'euclidean', inflate = self.p_rad + self.foot_rad)
			self.planner = PRMPlanner(self.map, distance = 'euclidean', inflate = self.p_rad + self.foot_rad, npoints = int((self.w*self.h)/100))
			self.p = [LinearPath([0, 0], [[0, 0]]) for _ in range(self.num_p)]
			self.p_path = [[] for _ in range(self.num_p)]
			self.p_sp = [0 for _ in range(self.num_p)]
			self.p_circle = [self.p_circles for _ in range(self.num_p)]

			Y, X = np.ogrid[-self.foot_rad:self.foot_rad+1, -self.foot_rad:self.foot_rad+1]
			dist_from_center = np.sqrt((X)**2 + (Y)**2)
			self.foot_mask = dist_from_center <= self.foot_rad
			# print(self.foot_mask)

		self.rooms = []
		self.regenerate_map()

	def regenerate_map(self):
		# map has an external wall
		if self.ext_wall:
			self.map = np.ones((self.h, self.w))
			self.map[self.wall_w:-self.wall_w, self.wall_w:-self.wall_w] = 0
			self.add_wall(self.wall_w, self.h-self.wall_w, self.wall_w, self.w-self.wall_w)
		# map has no external wall
		else:
			self.map = np.zeros((self.h, self.w))
			self.add_wall(0, self.h, 0, self.w)
		# regenerate pedestrians if needed
		if self.num_p > 0:
			self.planner = PRMPlanner(self.map, distance = 'euclidean', inflate = self.p_rad + self.foot_rad, npoints = int((self.w*self.h)/100))
			self.planner.plan()
			self.regenerate_pedestrians()

	def regenerate_pedestrians(self):
		for i in range(self.num_p):
			while True:
				try:
					start = (random.randrange(0, self.h), random.randrange(0, self.w))
					goal = (random.randrange(0, self.h), random.randrange(0, self.w))
					# self.planner.goal = goal
					self.p_path[i] = self.planner.query(start = start, goal = goal)
					self.p[i] = LinearPath(start, self.p_path[i][1:])
					self.p_sp[i] = random.uniform(self.p_min_sp, self.p_max_sp)
					break
				except ValueError:
					pass
				except RuntimeError:
					pass

	def add_wall(self, hmin, hmax, wmin, wmax, depth = 1):
		# plot the current map state
		# if depth > 1:
		# 	self.plot()

		# maximum depth reached
		if depth > self.max_depth:
			print('Max depth reached')
			self.rooms.append({"id": len(self.rooms), "x": [wmin, wmax-1], "y": [hmin, hmax-1]})
			return

		# room is too small to add wall
		if hmax - hmin < 2*self.min_room_dim + self.wall_w and wmax - wmin < 2*self.min_room_dim + self.wall_w:
			print('Room too small to divide')
			self.rooms.append({"id": len(self.rooms), "x": [wmin, wmax-1], "y": [hmin, hmax-1]})
			return

		# divide room with wall across bigger dimension (horizontally if botyh axis are equal)
		if (hmax-hmin) >= (wmax-wmin):
			self.add_wall_horizontal(hmin, hmax, wmin, wmax, depth)
		else:
			self.add_wall_vertical(hmin, hmax, wmin, wmax, depth)

	def add_wall_horizontal(self, hmin, hmax, wmin, wmax, depth, retry = 0):
		# cancel the wall after too many retries
		if retry == 10:
			print('Max number of retries reached, wall aborted.')
			return

		# create wall
		wall_pos = random.randint(hmin + self.min_room_dim, hmax - self.min_room_dim - self.wall_w)
		print('Horizontal Wall: ' + str(wall_pos))
		# check for doors on the sides
		if depth > 1 and sum(self.map[wall_pos:(wall_pos + self.wall_w), wmin - 1]) < self.wall_w or sum(self.map[wall_pos:(wall_pos + self.wall_w), wmax]) < self.wall_w:
			print('Wall blocking the door on try ' + str(retry))
			self.add_wall_horizontal(hmin, hmax, wmin, wmax, depth, retry + 1)
			return
		self.map[wall_pos:(wall_pos + self.wall_w), wmin:wmax] = 1

		# create door
		door_pos = random.randint(wmin + self.door_to_wall_min, wmax - self.door_to_wall_min - self.door_w)
		print('Door: ' + str(door_pos))
		self.map[wall_pos:(wall_pos + self.wall_w), door_pos:(door_pos + self.door_w)] = 0

		# further split created rooms
		self.add_wall(hmin, wall_pos, wmin, wmax, depth + 1)
		self.add_wall(wall_pos + self.wall_w, hmax, wmin, wmax, depth + 1)

	def add_wall_vertical(self, hmin, hmax, wmin, wmax, depth, retry = 0):
		# cancel the wall after too many retries
		if retry == 10:
			print('Max number of retries reached, wall aborted.')
			return

		# create wall
		wall_pos = random.randint(wmin + self.min_room_dim, wmax - self.min_room_dim - self.wall_w)
		print('Vertical Wall: ' + str(wall_pos))
		# check for doors on the sides
		if depth > 1 and sum(self.map[hmin - 1, wall_pos:(wall_pos + self.wall_w)]) < self.wall_w or sum(self.map[hmax, wall_pos:(wall_pos + self.wall_w)]) < self.wall_w:
			print('Wall blocking the door on try ' + str(retry))
			self.add_wall_vertical(hmin, hmax, wmin, wmax, depth, retry + 1)
			return
		self.map[hmin:hmax, wall_pos:(wall_pos + self.wall_w)] = 1

		# create door
		door_pos = random.randint(hmin + self.door_to_wall_min, hmax - self.door_to_wall_min - self.door_w)
		print('Door: ' + str(door_pos))
		self.map[door_pos:(door_pos + self.door_w), wall_pos:(wall_pos + self.wall_w)] = 0

		# further split created rooms
		self.add_wall(hmin, hmax, wmin, wall_pos, depth + 1)
		self.add_wall(hmin, hmax, wall_pos + self.wall_w, wmax, depth + 1)

	def step(self, dt):
		if self.num_p > 0:
			for i in range(self.num_p):
				pos, time_left = self.p[i].step(self.p_sp[i], dt)
				if time_left and self.p_circle[i]:
					while time_left:
						self.p_path[i] = np.flip(self.p_path[i], axis = 0)
						self.p[i] = LinearPath(self.p_path[i][0], self.p_path[i][1:])
						pos, time_left = self.p[i].step(self.p_sp[i], dt - time_left)
				if time_left and not self.p_circle[i]:
					while time_left:
						try:
							start = (random.randrange(0, self.h), random.randrange(0, self.w))
							goal = (random.randrange(0, self.h), random.randrange(0, self.w))
							# self.planner.goal = goal
							self.p_path[i] = self.planner.query(start = start, goal = goal)
							self.p[i] = LinearPath(start, self.p_path[i][1:])
							self.p_sp[i] = random.uniform(self.p_min_sp, self.p_max_sp)
							break
						except ValueError:
							pass
						except RuntimeError:
							pass

	def add_pedestrian(self, speed, path, planned, circle):
		if self.num_p == 0:
			self.planner = PRMPlanner(self.map, distance = 'euclidean', inflate = self.p_rad + self.foot_rad, npoints = int((self.w*self.h)/100))

		path = path*(1/self.res)

		start = (path[0][0], path[0][1])
		if not planned:
			goal = (path[1][0], path[1][1])
			path = self.planner.query(start = start, goal = goal)
		self.p_path.append(path)
		self.p.append(LinearPath(start, self.p_path[-1][1:]))
		if speed == 0:
			speed = random.uniform(self.p_min_sp, self.p_max_sp)
		self.p_sp.append(speed)
		self.p_circle.append(circle)

		self.num_p += 1


	def get_pedmap(self):
		m = np.zeros((self.h, self.w), dtype=np.bool)
		if self.num_p > 0:
			for p in self.p:
				dist = p.points[0] - p.pos
				angle = math.atan2(dist[1], dist[0])
				m[round(p.pos[1] + self.p_rad*math.sin(angle-math.pi/2))-self.foot_rad:round(p.pos[1] + self.p_rad*math.sin(angle-math.pi/2))+self.foot_rad+1,
					round(p.pos[0] + self.p_rad*math.cos(angle-math.pi/2))-self.foot_rad:round(p.pos[0] + self.p_rad*math.cos(angle-math.pi/2))+1+self.foot_rad] |= self.foot_mask
				m[round(p.pos[1] - self.p_rad*math.sin(angle-math.pi/2))-self.foot_rad:round(p.pos[1] - self.p_rad*math.sin(angle-math.pi/2))+self.foot_rad+1,
					round(p.pos[0] - self.p_rad*math.cos(angle-math.pi/2))-self.foot_rad:round(p.pos[0] - self.p_rad*math.cos(angle-math.pi/2))+1+self.foot_rad] |= self.foot_mask
		return np.maximum(m, self.map)


	def plot(self):
		rows, cols = np.shape(self.map)
		plt.figure()
		for row in range(rows):
			for col in range(cols):
				if self.map[row, col]:
					plt.plot(col, row, color = 'black', marker = 's', markersize = 1)
		if self.num_p > 0:
			for i in range(self.num_p):
				plt.plot(self.p_path[i].T[0], self.p_path[i].T[1], color = 'blue')
				plt.plot(self.p[i].pos[0], self.p[i].pos[1], color = 'blue', marker = 'o', markersize = 1)
		for r in self.rooms:
			plt.plot(r["x"], r["y"], color = "red")
			plt.text(mean(r["x"]), mean(r["y"]), str(r["id"]), c = 'red')
		plt.show()

	def save_map_to_pgm(self, mapname, add_timestamp = False):
		filename = mapname + ('' if not add_timestamp else '_' + '_'.join(str(datetime.now().timestamp()).split('.')))

		# save map as image
		im = Image.fromarray(np.uint8(255 - np.flip(self.map, axis=0)*255), 'L')
		im.save(filename + '.pgm')

		# save map parameters to file
		with open(filename + '.yaml', 'w') as f:
			f.write('image: ' + filename + '.pgm\nresolution: ' + str(self.res) + '\norigin: [0.0, 0.0, 0.0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n')

	def __str__(self):
		return str(self.map)

if __name__ == '__main__':

	parser = argparse.ArgumentParser()

	# map metadata
	parser.add_argument("--width", type = float, default = 15)
	parser.add_argument("--height", type = float, default = 15)
	parser.add_argument("--resolution", type = float, default = 0.1)

	# map creation arguments
	parser.add_argument("--wall_width", type = float, default = 0.3)
	parser.add_argument("--external_wall", type = bool, default = True)
	parser.add_argument("--min_room_dim", type = float, default = 3)
	parser.add_argument("--door_width", type = float, default = 1)
	parser.add_argument("--door_to_wall_min", type = float, default = 0.2)
	parser.add_argument("--max_depth", type = int, default = 4)

	# pedestrian creation arguments
	parser.add_argument("--num_of_pedestrians", type = int, default = 5)
	parser.add_argument("--pedestrian_min_speed", type = float, default = 0.5)
	parser.add_argument("--pedestrian_max_speed", type = float, default = 2)
	parser.add_argument("--pedestrian_radius", type = float, default = 0.2)
	parser.add_argument("--pedestrian_foot_radius", type = float, default = 0.1)
	parser.add_argument("--pedestrian_walk_circles", type = bool, default = False)

	# node arguments
	parser.add_argument("--publish", type = bool, default = True)
	parser.add_argument("--publish_rate", type = int, default = 100)
	parser.add_argument("--auto_step", type = bool, default = False)
	parser.add_argument("--publish_on_step", type = bool, default = False)

	args = parser.parse_args()

	# rms = RandomMapServerWithPedestrians(args)
	# rms.save_map_to_pgm('random_map', False)
	# rms.plot()
	# plt.savefig('random_map.jpg')

	# while(True):
	# 	rms.step(10)
	# 	rms.plot()

	rospy.init_node('random_map_test')
	node = RandomMapServerNode(args)
	node.rms.plot()
	rospy.spin()
